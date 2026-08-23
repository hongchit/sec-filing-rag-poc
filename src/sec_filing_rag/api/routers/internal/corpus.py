from __future__ import annotations

import uuid
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends

from ....schemas.internal import CorpusExecutionResponse, ItemExecutionRequest
from ....services.workflows import FilingExecutionService
from ...dependencies import execution_service

router = APIRouter()


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
