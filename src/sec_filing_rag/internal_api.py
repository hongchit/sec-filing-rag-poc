from __future__ import annotations

import uuid
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException

from .dependencies import authorize_internal, execution_service, workflow_repository
from .domain import safe_error
from .internal_models import (
    AcquisitionResponse,
    BatchFinalizationRequest,
    CorpusExecutionResponse,
    FilingSelectionResponse,
    ItemExecutionRequest,
    ItemFailureRequest,
)
from .workflow_repository import WorkflowRepository
from .workflow_services import FilingExecutionService

router = APIRouter(prefix="/internal", dependencies=[Depends(authorize_internal)])


@router.get("/filing-batches/{batch_id}", tags=["internal-lifecycle"], operation_id="getFilingBatchExecution")
def get_execution_batch(
    batch_id: uuid.UUID, repository: Annotated[WorkflowRepository, Depends(workflow_repository)]
) -> dict[str, object]:
    result = repository.batch(batch_id)
    if result is None:
        raise HTTPException(status_code=404, detail="filing batch not found")
    return result


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
        acquisition_id, accession, checksum, size = service.acquire(item_id, payload.kestra_execution_id)
        return AcquisitionResponse(
            acquisition_id=acquisition_id, accession=accession, checksum=checksum, size=size
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post(
    "/corpus-executions/{item_id}",
    response_model=CorpusExecutionResponse,
    tags=["internal-corpus-execution"],
    operation_id="executeCorpusForBatchItem",
    description="Build a corpus from a persisted acquisition and promote only in latest mode.",
)
def process(
    item_id: uuid.UUID,
    payload: ItemExecutionRequest,
    service: Annotated[FilingExecutionService, Depends(execution_service)],
) -> CorpusExecutionResponse:
    status, corpus_id, promoted, error = service.process(item_id, payload.kestra_execution_id)
    return CorpusExecutionResponse(
        item_id=item_id,
        status=cast(Literal["succeeded", "skipped", "failed"], status),
        corpus_version_id=corpus_id,
        promoted=promoted,
        error=error,
    )


@router.post(
    "/filing-items/{item_id}/failures",
    tags=["internal-lifecycle"],
    operation_id="failFilingBatchItem",
    description="Record a safe terminal item failure after an orchestration error.",
)
def fail_item(
    item_id: uuid.UUID,
    payload: ItemFailureRequest,
    repository: Annotated[WorkflowRepository, Depends(workflow_repository)],
) -> dict[str, str]:
    repository.transition(
        item_id, "failed", error=safe_error(payload.error), execution_id=payload.kestra_execution_id
    )
    return {"status": "failed"}


@router.post(
    "/filing-batches/{batch_id}/finalizations",
    tags=["internal-lifecycle"],
    operation_id="finalizeFilingBatch",
    description="Finalize aggregate state and fail any stranded running items.",
)
def finalize(
    batch_id: uuid.UUID,
    payload: BatchFinalizationRequest,
    repository: Annotated[WorkflowRepository, Depends(workflow_repository)],
) -> dict[str, str]:
    return {"status": repository.finalize(batch_id, payload.kestra_execution_id)}
