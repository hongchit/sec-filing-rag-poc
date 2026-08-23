from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ....domain.filings import safe_error
from ....repositories.workflows import WorkflowRepository
from ....schemas.internal import BatchFinalizationRequest, ItemFailureRequest
from ....schemas.system import StatusResponse
from ....schemas.workflows import FilingBatchStatus
from ...dependencies import workflow_repository

router = APIRouter()


@router.get(
    "/filing-batches/{batch_id}",
    response_model=FilingBatchStatus,
    tags=["internal-lifecycle"],
    operation_id="getFilingBatchExecution",
)
def get_execution_batch(
    batch_id: uuid.UUID, repository: Annotated[WorkflowRepository, Depends(workflow_repository)]
) -> FilingBatchStatus:
    result = repository.batch(batch_id)
    if result is None:
        raise HTTPException(status_code=404, detail="filing batch not found")
    return FilingBatchStatus.model_validate(result)


@router.post(
    "/filing-items/{item_id}/failures",
    response_model=StatusResponse,
    tags=["internal-lifecycle"],
    operation_id="failFilingBatchItem",
    description="Record a safe terminal item failure after an orchestration error.",
)
def fail_item(
    item_id: uuid.UUID,
    payload: ItemFailureRequest,
    repository: Annotated[WorkflowRepository, Depends(workflow_repository)],
) -> StatusResponse:
    repository.transition(
        item_id, "failed", error=safe_error(payload.error), execution_id=payload.kestra_execution_id
    )
    return StatusResponse(status="failed")


@router.post(
    "/filing-batches/{batch_id}/finalizations",
    response_model=StatusResponse,
    tags=["internal-lifecycle"],
    operation_id="finalizeFilingBatch",
    description="Finalize aggregate state and fail any stranded running items.",
)
def finalize(
    batch_id: uuid.UUID,
    payload: BatchFinalizationRequest,
    repository: Annotated[WorkflowRepository, Depends(workflow_repository)],
) -> StatusResponse:
    return StatusResponse(status=repository.finalize(batch_id, payload.kestra_execution_id))
