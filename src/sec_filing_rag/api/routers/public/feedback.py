from __future__ import annotations

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException

from ....generation.service import ResearchService
from ....schemas.research import FeedbackCreate, FeedbackResponse
from ...dependencies import research_service

router = APIRouter(tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse)
def save_feedback(
    body: FeedbackCreate, service: Annotated[ResearchService, Depends(research_service)]
) -> dict[str, Any]:
    if service.repository.get(body.result_id) is None:
        raise HTTPException(404, detail="research not found")
    return cast(
        dict[str, Any],
        service.repository.save_feedback(body.result_id, body.rating, body.comment),  # type: ignore[attr-defined]
    )
