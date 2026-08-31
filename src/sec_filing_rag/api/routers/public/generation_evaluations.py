from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ....evaluation.dashboard import ArtifactConflict, ArtifactMissing
from ....evaluation.generation_dashboard import (
    GenerationEvaluationCases,
    GenerationEvaluationChunk,
    GenerationEvaluationDashboardService,
    GenerationEvaluationQuestion,
    GenerationEvaluationSummary,
    GenerationPromptSource,
)
from ...dependencies import generation_evaluation_dashboard

router = APIRouter(prefix="/generation-evaluations/current", tags=["generation-evaluations"])
Service = Annotated[GenerationEvaluationDashboardService, Depends(generation_evaluation_dashboard)]


def translate(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404 if isinstance(exc, ArtifactMissing) else 409, detail=str(exc))


@router.get("", response_model=GenerationEvaluationSummary, operation_id="getCurrentGenerationEvaluation")
def current(service: Service) -> GenerationEvaluationSummary:
    """Read the current portable generation evaluation summary."""
    try:
        return service.summary()
    except (ArtifactMissing, ArtifactConflict) as exc:
        raise translate(exc) from exc


@router.get("/cases", response_model=GenerationEvaluationCases, operation_id="getCurrentGenerationEvaluationCases")
def cases(service: Service) -> GenerationEvaluationCases:
    """Read question-by-prompt verdicts for the current generation evaluation."""
    try:
        return service.cases()
    except (ArtifactMissing, ArtifactConflict) as exc:
        raise translate(exc) from exc


@router.get("/questions/{case_id}", response_model=GenerationEvaluationQuestion, operation_id="getCurrentGenerationEvaluationQuestion")
def question(case_id: str, service: Service) -> GenerationEvaluationQuestion:
    """Compare every generated answer for one reviewed question."""
    try:
        return service.question(case_id)
    except (ArtifactMissing, ArtifactConflict) as exc:
        raise translate(exc) from exc


@router.get("/prompts/{prompt_id}", response_model=GenerationPromptSource, operation_id="getCurrentGenerationEvaluationPrompt")
def prompt(prompt_id: str, service: Service) -> GenerationPromptSource:
    """Read checksum-verified source for one evaluated prompt."""
    try:
        return service.prompt(prompt_id)
    except (ArtifactMissing, ArtifactConflict) as exc:
        raise translate(exc) from exc


@router.get("/chunks/{chunk_id}", response_model=GenerationEvaluationChunk, operation_id="getCurrentGenerationEvaluationChunk")
def chunk(chunk_id: str, service: Service) -> GenerationEvaluationChunk:
    """Read optional database-backed evidence referenced by the generation run."""
    try:
        return service.chunk(chunk_id)
    except (ArtifactMissing, ArtifactConflict) as exc:
        raise translate(exc) from exc
