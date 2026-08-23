from __future__ import annotations

import hmac
from functools import lru_cache
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..core.config import Settings
from ..core.resources import AppResources
from ..integrations.kestra import KestraGateway
from ..integrations.sec import EdgarGateway, configure_edgartools
from ..repositories.companies import CompanyRepository
from ..repositories.corpus import IngestionRepository
from ..repositories.database import Database
from ..repositories.system import SystemRepository
from ..repositories.workflows import WorkflowRepository
from ..services.ingestion import IngestionPipeline
from ..services.workflows import FilingBatchService, FilingExecutionService


@lru_cache
def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def resources(request: Request) -> AppResources:
    return cast(AppResources, request.app.state.resources)


def database(app_resources: Annotated[AppResources, Depends(resources)]) -> Database:
    return app_resources.database


def system_repository(db: Annotated[Database, Depends(database)]) -> SystemRepository:
    return SystemRepository(db)


def company_repository(db: Annotated[Database, Depends(database)]) -> CompanyRepository:
    return CompanyRepository(db)


def ingestion_repository(db: Annotated[Database, Depends(database)]) -> IngestionRepository:
    return IngestionRepository(db)


def workflow_repository(db: Annotated[Database, Depends(database)]) -> WorkflowRepository:
    return WorkflowRepository(db)


def provider_gateway() -> EdgarGateway:
    config = settings()
    return EdgarGateway(
        facade=configure_edgartools(
            config.edgar_identity, config.edgar_rate_limit_per_sec, config.edgar_access_mode
        )
    )


def batch_service(
    repository: Annotated[WorkflowRepository, Depends(workflow_repository)],
    ingestion: Annotated[IngestionRepository, Depends(ingestion_repository)],
    app_resources: Annotated[AppResources, Depends(resources)],
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
    return FilingBatchService(config, repository, kestra, ingestion)


def execution_service(
    repository: Annotated[WorkflowRepository, Depends(workflow_repository)],
    ingestion: Annotated[IngestionRepository, Depends(ingestion_repository)],
    provider: Annotated[EdgarGateway, Depends(provider_gateway)],
    app_resources: Annotated[AppResources, Depends(resources)],
) -> FilingExecutionService:
    config = settings()
    pipeline = IngestionPipeline(config, ingestion, app_resources.openai)
    return FilingExecutionService(config, repository, provider, pipeline)


_internal_bearer = HTTPBearer(auto_error=False, scheme_name="InternalBearer")


def authorize_internal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_internal_bearer)],
    config: Annotated[Settings, Depends(settings)],
) -> None:
    expected = config.ingestion_api_token
    supplied = (
        credentials.credentials if credentials is not None and credentials.scheme.lower() == "bearer" else ""
    )
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid ingestion token")
