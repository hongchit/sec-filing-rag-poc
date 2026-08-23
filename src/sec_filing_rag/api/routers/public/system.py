from __future__ import annotations

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ....repositories.system import SystemRepository
from ....schemas.system import HealthResponse
from ...dependencies import system_repository

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
    operation_id="getHealth",
    description="Check application database readiness.",
)
def health(repository: Annotated[SystemRepository, Depends(system_repository)]) -> HealthResponse:
    if not repository.ready():
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail={"process": "ok", "application_database": "unavailable"},
        )
    return HealthResponse()
