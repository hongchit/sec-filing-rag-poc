from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ....schemas.internal import AcquisitionResponse, FilingSelectionResponse, ItemExecutionRequest
from ....services.workflows import FilingExecutionService
from ...dependencies import execution_service

router = APIRouter()


@router.post(
    "/providers/filing-items/{item_id}/selection",
    response_model=FilingSelectionResponse,
    tags=["internal-provider-execution"],
    operation_id="selectFilingForBatchItem",
    description="Select the latest original 10-K or an exact SEC report-date year.",
)
def select(
    item_id: uuid.UUID,
    payload: ItemExecutionRequest,
    service: Annotated[FilingExecutionService, Depends(execution_service)],
) -> FilingSelectionResponse:
    try:
        accession, year = service.select(item_id, payload.kestra_execution_id)
        return FilingSelectionResponse(
            item_id=item_id,
            status="selected" if accession else "skipped",
            accession=accession,
            fiscal_year=year,
            reason=None if accession else "exact fiscal year unavailable",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post(
    "/providers/filing-items/{item_id}/acquisitions",
    response_model=AcquisitionResponse,
    tags=["internal-provider-execution"],
    operation_id="acquireSelectedFiling",
    description="Validate and persist selected filing HTML; return only a safe acquisition reference.",
)
def acquire(
    item_id: uuid.UUID,
    payload: ItemExecutionRequest,
    service: Annotated[FilingExecutionService, Depends(execution_service)],
) -> AcquisitionResponse:
    try:
        acquisition_id, accession, checksum, size = service.acquire(
            item_id, payload.kestra_execution_id
        )
        return AcquisitionResponse(
            acquisition_id=acquisition_id, accession=accession, checksum=checksum, size=size
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
