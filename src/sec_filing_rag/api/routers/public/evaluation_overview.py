from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ....evaluation.dashboard import ArtifactConflict, ArtifactMissing
from ....evaluation.overview import EvaluationOverview, EvaluationOverviewService
from ...dependencies import evaluation_overview

router = APIRouter(prefix="/evaluation-overview", tags=["evaluation-overview"])
Service = Annotated[EvaluationOverviewService, Depends(evaluation_overview)]


@router.get(
    "/current", response_model=EvaluationOverview, operation_id="getCurrentEvaluationOverview"
)
def current(service: Service) -> EvaluationOverview:
    """Read safe aggregate results and model provenance for the public portfolio overview."""
    try:
        return service.current()
    except (ArtifactMissing, ArtifactConflict) as exc:
        raise HTTPException(
            404 if isinstance(exc, ArtifactMissing) else 409, detail=str(exc)
        ) from exc
