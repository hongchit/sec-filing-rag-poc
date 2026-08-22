from __future__ import annotations

import hmac
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings
from .kestra import KestraGateway
from .pipeline import IngestionPipeline
from .repositories import Database
from .sec import EdgarGateway, configure_edgartools
from .store import Store
from .workflow_repository import WorkflowRepository
from .workflow_services import FilingBatchService, FilingExecutionService


@lru_cache
def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def store() -> Store:
    return Store(settings().database_url)


def workflow_repository() -> WorkflowRepository:
    return WorkflowRepository(Database(settings().database_url))


def provider_gateway() -> EdgarGateway:
    config = settings()
    return EdgarGateway(
        facade=configure_edgartools(
            config.edgar_identity, config.edgar_rate_limit_per_sec, config.edgar_access_mode
        )
    )


def batch_service() -> FilingBatchService:
    config = settings()
    return FilingBatchService(
        config,
        workflow_repository(),
        KestraGateway(
            api_url=config.kestra_api_url,
            namespace=config.kestra_namespace,
            flow_id=config.kestra_batch_flow_id,
            username=config.kestra_basic_auth_username,
            password=config.kestra_basic_auth_password,
            timeout=config.kestra_timeout_seconds,
            retries=config.kestra_max_retries,
        ),
        store(),
    )


def execution_service() -> FilingExecutionService:
    config = settings()
    db = store()
    return FilingExecutionService(
        config, workflow_repository(), provider_gateway(), IngestionPipeline(config, db)
    )


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
