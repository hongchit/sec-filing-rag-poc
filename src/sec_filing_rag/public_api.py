from __future__ import annotations

import uuid
from http import HTTPStatus
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .config import TICKER_RE, load_companies
from .dependencies import batch_service, settings, store, workflow_repository
from .store import Store
from .workflow_models import (
    FilingBatchAccepted,
    FilingBatchRequest,
    FilingBatchStatus,
    FilingPreparationRequest,
)
from .workflow_repository import WorkflowRepository
from .workflow_services import FilingBatchService

router = APIRouter(prefix="/api")


def _submit(
    payload: FilingBatchRequest, request: Request, service: FilingBatchService
) -> FilingBatchAccepted:
    try:
        batch_id, execution_id, tickers = service.submit(
            tickers=payload.tickers,
            fiscal_year=payload.fiscal_year,
            request_id=request.state.request_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    return FilingBatchAccepted(
        batch_id=batch_id,
        kestra_execution_id=execution_id,
        mode="exact_year" if payload.fiscal_year is not None else "latest",
        fiscal_year=payload.fiscal_year,
        tickers=tickers,
    )


@router.get(
    "/health", tags=["system"], operation_id="getHealth", description="Check application database readiness."
)
def health(db: Annotated[Store, Depends(store)]) -> dict[str, str]:
    if not db.ready():
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail={"process": "ok", "application_database": "unavailable"},
        )
    return {"process": "ok", "application_database": "ready"}


@router.get(
    "/companies",
    tags=["companies"],
    operation_id="listCompanies",
    description="List configured companies and corpus readiness.",
)
def companies(db: Annotated[Store, Depends(store)]) -> list[dict[str, Any]]:
    configured = load_companies(settings().company_config_path).companies
    stored = {entry["ticker"]: entry for entry in db.companies()}
    return [
        {
            **stored.get(entry.ticker, {"ticker": entry.ticker, "resolution_status": "pending"}),
            "enabled": entry.enabled,
        }
        for entry in configured
    ]


@router.get(
    "/companies/{ticker}/status",
    tags=["companies"],
    operation_id="getCompanyStatus",
    description="Inspect application-owned corpus status without querying Kestra.",
)
def company_status(ticker: str, db: Annotated[Store, Depends(store)]) -> dict[str, Any]:
    normalized = ticker.strip().upper()
    if not TICKER_RE.fullmatch(normalized):
        raise HTTPException(status_code=422, detail="invalid ticker")
    configured = {entry.ticker: entry for entry in load_companies(settings().company_config_path).companies}
    if normalized not in configured:
        raise HTTPException(status_code=404, detail="unknown configured ticker")
    result = db.company_status(normalized) or {
        "ticker": normalized,
        "active_corpus": None,
        "coverage": [],
        "latest_run": None,
    }
    return {**result, "enabled": configured[normalized].enabled}


@router.post(
    "/filing-batches",
    response_model=FilingBatchAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["filing-workflows"],
    operation_id="createFilingBatch",
    description="Submit all enabled companies or an explicit ordered ticker subset for latest or exact-year ingestion.",
)
def create_batch(
    payload: FilingBatchRequest,
    request: Request,
    service: Annotated[FilingBatchService, Depends(batch_service)],
) -> FilingBatchAccepted:
    return _submit(payload, request, service)


@router.post(
    "/companies/{ticker}/filing-preparations",
    response_model=FilingBatchAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["filing-workflows"],
    operation_id="createCompanyFilingPreparation",
    description="Submit one configured company for latest or exact fiscal-year ingestion.",
)
def create_preparation(
    ticker: str,
    payload: FilingPreparationRequest,
    request: Request,
    service: Annotated[FilingBatchService, Depends(batch_service)],
) -> FilingBatchAccepted:
    try:
        normalized = ticker.strip().upper()
        if not TICKER_RE.fullmatch(normalized):
            raise ValueError("invalid ticker")
        return _submit(
            FilingBatchRequest(tickers=[normalized], fiscal_year=payload.fiscal_year), request, service
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get(
    "/filing-batches/{batch_id}",
    response_model=FilingBatchStatus,
    tags=["filing-workflows"],
    operation_id="getFilingBatch",
    description="Read authoritative overall and per-company workflow status.",
)
def get_batch(
    batch_id: uuid.UUID, repository: Annotated[WorkflowRepository, Depends(workflow_repository)]
) -> FilingBatchStatus:
    result = repository.batch(batch_id)
    if result is None:
        raise HTTPException(status_code=404, detail="filing batch not found")
    return FilingBatchStatus.model_validate(result)
