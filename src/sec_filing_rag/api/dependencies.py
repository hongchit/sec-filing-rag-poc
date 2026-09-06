from __future__ import annotations

import hmac
from functools import lru_cache
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer

from ..auth import AuthRepository, Principal
from ..core.config import Settings
from ..core.pricing import load_pricing_configuration
from ..core.resources import AppResources
from ..evaluation.dashboard import EvaluationDashboardService
from ..evaluation.generation_dashboard import GenerationEvaluationDashboardService
from ..evaluation.overview import EvaluationOverviewService
from ..generation.service import (
    OpenAIAnswerProvider,
    ResearchService,
    load_generation_configuration,
)
from ..integrations.kestra import KestraGateway
from ..integrations.sec import EdgarGateway, configure_edgartools
from ..repositories.companies import CompanyRepository
from ..repositories.corpus import IngestionRepository
from ..repositories.corpus_reader import CorpusReaderRepository
from ..repositories.database import Database
from ..repositories.model_executions import ModelExecutionRepository
from ..repositories.research import ResearchRepository
from ..repositories.system import SystemRepository
from ..repositories.workflows import WorkflowRepository
from ..retrieval.service import (
    OpenAIQueryEmbedder,
    RetrievalRepository,
    RetrievalService,
    load_retrieval_configuration,
)
from ..services.ingestion import IngestionPipeline
from ..services.workflows import (
    FilingBatchCreator,
    FilingBatchService,
    FilingExecutionService,
    ScheduledFilingBatchService,
)


@lru_cache
def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def resources(request: Request) -> AppResources:
    return cast(AppResources, request.app.state.resources)


def database(app_resources: Annotated[AppResources, Depends(resources)]) -> Database:
    return app_resources.database


def auth_repository(db: Annotated[Database, Depends(database)]) -> AuthRepository:
    return AuthRepository(db)


_session_cookie = APIKeyCookie(
    name="__Host-sec-rag-session", auto_error=False, scheme_name="SessionCookie"
)


def current_user(
    request: Request,
    repository: Annotated[AuthRepository, Depends(auth_repository)],
    config: Annotated[Settings, Depends(settings)],
    documented_cookie: Annotated[str | None, Security(_session_cookie)] = None,
) -> Principal:
    token = documented_cookie or request.cookies.get("sec-rag-session")
    csrf = (
        request.headers.get("X-CSRF-Token")
        if request.method not in {"GET", "HEAD", "OPTIONS"}
        else None
    )
    if not token:
        raise HTTPException(status_code=401, detail={"code": "authentication_required"})
    principal = repository.authenticate(token, csrf, config.admin_emails)
    if principal is None:
        detail = (
            {"code": "invalid_csrf"} if csrf is not None else {"code": "authentication_required"}
        )
        raise HTTPException(status_code=403 if csrf is not None else 401, detail=detail)
    request.state.user = principal
    return principal


def require_admin(user: Annotated[Principal, Depends(current_user)]) -> Principal:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail={"code": "administrator_required"})
    return user


def system_repository(db: Annotated[Database, Depends(database)]) -> SystemRepository:
    return SystemRepository(db)


def company_repository(db: Annotated[Database, Depends(database)]) -> CompanyRepository:
    return CompanyRepository(db)


def ingestion_repository(db: Annotated[Database, Depends(database)]) -> IngestionRepository:
    return IngestionRepository(db)


def corpus_reader_repository(
    db: Annotated[Database, Depends(database)],
) -> CorpusReaderRepository:
    return CorpusReaderRepository(db)


def workflow_repository(db: Annotated[Database, Depends(database)]) -> WorkflowRepository:
    return WorkflowRepository(db)


def model_execution_repository(
    db: Annotated[Database, Depends(database)], config: Annotated[Settings, Depends(settings)]
) -> ModelExecutionRepository:
    return ModelExecutionRepository(
        db, load_pricing_configuration(config.model_pricing_config_path)
    )


def filing_batch_creator(
    repository: Annotated[WorkflowRepository, Depends(workflow_repository)],
    ingestion: Annotated[IngestionRepository, Depends(ingestion_repository)],
) -> FilingBatchCreator:
    config = settings()
    return FilingBatchCreator(
        config,
        repository,
        ingestion,
        config.default_user_lifetime_budget_usd,
        config.corpus_preparation_cost_reservation_usd,
        load_pricing_configuration(config.model_pricing_config_path),
    )


def evaluation_dashboard(
    db: Annotated[Database, Depends(database)], config: Annotated[Settings, Depends(settings)]
) -> EvaluationDashboardService:
    return EvaluationDashboardService(db, config)


def generation_evaluation_dashboard(
    db: Annotated[Database, Depends(database)], config: Annotated[Settings, Depends(settings)]
) -> GenerationEvaluationDashboardService:
    return GenerationEvaluationDashboardService(db, config)


def evaluation_overview(
    retrieval: Annotated[EvaluationDashboardService, Depends(evaluation_dashboard)],
    generation: Annotated[
        GenerationEvaluationDashboardService, Depends(generation_evaluation_dashboard)
    ],
    config: Annotated[Settings, Depends(settings)],
) -> EvaluationOverviewService:
    return EvaluationOverviewService(retrieval, generation, config)


def provider_gateway() -> EdgarGateway:
    config = settings()
    return EdgarGateway(
        facade=configure_edgartools(
            config.edgar_identity, config.edgar_rate_limit_per_sec, config.edgar_access_mode
        )
    )


def batch_service(
    creator: Annotated[FilingBatchCreator, Depends(filing_batch_creator)],
    repository: Annotated[WorkflowRepository, Depends(workflow_repository)],
    app_resources: Annotated[AppResources, Depends(resources)],
    user: Annotated[Principal, Depends(current_user)],
) -> FilingBatchService:
    config = settings()
    kestra = KestraGateway(
        api_url=config.kestra_api_url,
        namespace=config.kestra_namespace,
        flow_id=config.kestra_batch_flow_id,
        username=config.kestra_basic_auth_username,
        password=config.kestra_basic_auth_password,
        timeout=config.kestra_timeout_seconds,
        retries=config.kestra_max_retries,
        client=app_resources.http,
    )
    return FilingBatchService(
        config,
        creator,
        repository,
        kestra,
        user.id,
    )


def scheduled_batch_service(
    creator: Annotated[FilingBatchCreator, Depends(filing_batch_creator)],
    auth: Annotated[AuthRepository, Depends(auth_repository)],
) -> ScheduledFilingBatchService:
    return ScheduledFilingBatchService(settings(), creator, auth)


def execution_service(
    repository: Annotated[WorkflowRepository, Depends(workflow_repository)],
    ingestion: Annotated[IngestionRepository, Depends(ingestion_repository)],
    provider: Annotated[EdgarGateway, Depends(provider_gateway)],
    app_resources: Annotated[AppResources, Depends(resources)],
) -> FilingExecutionService:
    config = settings()
    pipeline = IngestionPipeline(config, ingestion, app_resources.openai)
    return FilingExecutionService(config, repository, provider, pipeline)


def research_service(
    db: Annotated[Database, Depends(database)],
    app_resources: Annotated[AppResources, Depends(resources)],
    config: Annotated[Settings, Depends(settings)],
    user: Annotated[Principal, Depends(current_user)],
) -> ResearchService:
    retrieval_config = load_retrieval_configuration(config.retrieval_config_path)
    generation_config = load_generation_configuration(config.generation_config_path)
    pricing_config = load_pricing_configuration(config.model_pricing_config_path)
    embedder = OpenAIQueryEmbedder(
        db,
        config.openai_api_key,
        retrieval_config.embedding_model,
        retrieval_config.embedding_dimensions,
        config.openai_timeout_seconds,
        client=app_resources.openai,
    )
    retrieval = RetrievalService(RetrievalRepository(db), embedder, retrieval_config)
    return ResearchService(
        ResearchRepository(db),
        retrieval,
        OpenAIAnswerProvider(app_resources.openai),
        generation_config,
        config.openai_chat_model,
        pricing_config,
        config.openai_embedding_model,
        user.id,
        config.default_user_lifetime_budget_usd,
        config.research_cost_reservation_usd,
    )


_internal_bearer = HTTPBearer(auto_error=False, scheme_name="InternalBearer")


def authorize_internal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_internal_bearer)],
    config: Annotated[Settings, Depends(settings)],
) -> None:
    expected = config.ingestion_api_token
    supplied = (
        credentials.credentials
        if credentials is not None and credentials.scheme.lower() == "bearer"
        else ""
    )
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid ingestion token"
        )
