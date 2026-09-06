from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ....evaluation.dashboard import (
    ArtifactConflict,
    ArtifactMissing,
    EvaluationCases,
    EvaluationChunk,
    EvaluationDashboardService,
    EvaluationSummary,
)
from ...dependencies import current_user, evaluation_dashboard

router = APIRouter(prefix="/retrieval-evaluations/current", tags=["retrieval-evaluations"])
protected = APIRouter(dependencies=[Depends(current_user)])
Service = Annotated[EvaluationDashboardService, Depends(evaluation_dashboard)]


def translate(exc: Exception) -> HTTPException:
    if isinstance(exc, ArtifactMissing):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=409, detail=str(exc))


@router.get("", response_model=EvaluationSummary, operation_id="getCurrentRetrievalEvaluation")
def current(service: Service) -> EvaluationSummary:
    """Read the validated current retrieval evaluation and official leaderboard."""
    try:
        return service.summary()
    except (ArtifactMissing, ArtifactConflict) as exc:
        raise translate(exc) from exc


@protected.get(
    "/configurations/{configuration_id}/cases",
    response_model=EvaluationCases,
    operation_id="getCurrentRetrievalEvaluationCases",
)
def cases(configuration_id: str, service: Service) -> EvaluationCases:
    """Inspect every reviewed question and ranked chunk for one stable configuration."""
    try:
        return service.cases(configuration_id)
    except (ArtifactMissing, ArtifactConflict) as exc:
        raise translate(exc) from exc


@protected.get(
    "/chunks/{chunk_id}",
    response_model=EvaluationChunk,
    operation_id="getCurrentRetrievalEvaluationChunk",
)
def chunk(chunk_id: str, service: Service) -> EvaluationChunk:
    """Lazy-load full text and provenance for a chunk referenced by the current evaluation."""
    try:
        return service.chunk(chunk_id)
    except (ArtifactMissing, ArtifactConflict) as exc:
        raise translate(exc) from exc


router.include_router(protected)
