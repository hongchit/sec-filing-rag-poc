from __future__ import annotations

import secrets
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel

from ..core.config import Settings
from ..generation.service import load_generation_configuration
from ..retrieval.service import load_retrieval_configuration
from .dashboard import EvaluationDashboardService, configuration_id
from .generation_dashboard import GenerationEvaluationDashboardService


class EvaluationOverviewExample(BaseModel):
    case_id: str
    question: str
    ticker: str
    accession: str
    corpus_version_id: str
    items: list[str]
    goal: str
    query_type: str
    consensus: bool
    interpretation: str
    citations: list[str]
    prompt_id: str
    judge_label: Literal["RELEVANT"]


class EvaluationOverview(BaseModel):
    benchmark: dict[str, Any]
    retrieval: dict[str, Any]
    generation: dict[str, Any]
    models: list[dict[str, Any]]
    example: EvaluationOverviewExample | None
    warnings: list[dict[str, Any]]


def _rank_buckets(questions: list[dict[str, Any]]) -> dict[str, int]:
    ranks = [float(question["reciprocal_rank"]) for question in questions]
    return {
        "rank_one": sum(rank == 1 for rank in ranks),
        "rank_two_three": sum(rank in {0.5, 1 / 3} for rank in ranks),
        "rank_four_ten": sum(0 < rank < 1 / 3 for rank in ranks),
        "not_found": sum(rank == 0 for rank in ranks),
    }


class EvaluationOverviewService:
    """Build a deliberately limited public view from validated evaluation artifacts."""

    def __init__(
        self,
        retrieval: EvaluationDashboardService,
        generation: GenerationEvaluationDashboardService,
        settings: Settings,
    ) -> None:
        self.retrieval = retrieval
        self.generation = generation
        self.settings = settings

    def current(self) -> EvaluationOverview:
        retrieval_result, cases, manifest = self.retrieval._load()
        generation_artifact, generation_cases = self.generation._load()
        retrieval_summary = self.retrieval.summary()
        generation_summary = self.generation.summary()

        selected_retrieval = next(
            row
            for row in retrieval_result.results
            if row["configuration"] == retrieval_result.selected_default
        )
        ranked = self.retrieval._configs(retrieval_result)
        baseline_rows: dict[str, dict[str, Any]] = {}
        for strategy in ("keyword", "vector"):
            best_id = retrieval_summary.strategy_best[strategy]
            config = next(row for row in ranked if row["id"] == best_id)
            artifact_row = next(
                row
                for row in retrieval_result.results
                if configuration_id(row["configuration"]) == best_id
            )
            baseline_rows[strategy] = {
                "configuration_id": best_id,
                "strategy": strategy,
                "hit_count": sum(
                    float(q["reciprocal_rank"]) > 0 for q in artifact_row["questions"]
                ),
                "mrr": artifact_row["mrr"],
                "rank_buckets": _rank_buckets(artifact_row["questions"]),
                "median_latency_ms": artifact_row["median_latency_ms"],
                "configuration": config,
            }

        prompt = next(
            (
                row
                for row in generation_summary.prompts
                if row["id"] == generation_summary.selected_prompt_id
            ),
            generation_summary.prompts[0] if generation_summary.prompts else None,
        )
        selected_prompt = generation_artifact.selected_prompt_id
        by_prompt = {
            candidate.prompt_id: {result.case_id: result for result in candidate.cases}
            for candidate in generation_artifact.prompts
        }
        example: EvaluationOverviewExample | None = None
        if selected_prompt and selected_prompt in by_prompt:
            selected_results = by_prompt[selected_prompt]
            candidates: list[tuple[Any, Any, Any]] = []
            for case in generation_cases:
                result = selected_results[case.id]
                interpretation = (
                    next(
                        (
                            paragraph
                            for paragraph in result.answer.paragraphs
                            if paragraph.kind == "interpretation"
                        ),
                        None,
                    )
                    if result.answer
                    else None
                )
                valid = (
                    result.judge is not None
                    and result.judge.label == "RELEVANT"
                    and result.failure is None
                    and result.answer is not None
                    and result.answer.disposition == "answered"
                    and not result.answer.insufficient_evidence
                    and not result.answer.policy_refusal
                    and interpretation is not None
                    and result.citation_audit.citation_handles
                    == result.citation_audit.valid_citation_handles
                    and result.citation_audit.cross_corpus_citations == 0
                )
                if not valid:
                    continue
                consensus = True
                for prompt_results in by_prompt.values():
                    judge = prompt_results[case.id].judge
                    if judge is None or judge.label != "RELEVANT":
                        consensus = False
                        break
                if consensus:
                    candidates.append((case, result, interpretation))
            if candidates:
                chosen, chosen_result, interpretation = secrets.choice(candidates)
                example = EvaluationOverviewExample(
                    case_id=chosen.id,
                    question=chosen.question,
                    ticker=chosen.ticker,
                    accession=chosen.accession,
                    corpus_version_id=str(chosen.corpus_version_id),
                    items=sorted(chosen.allowed_items),
                    goal=chosen.goal,
                    query_type=chosen.query_type,
                    consensus=True,
                    interpretation=interpretation.text,
                    citations=interpretation.citations,
                    prompt_id=selected_prompt,
                    judge_label=chosen_result.judge.label,
                )

        active_retrieval = load_retrieval_configuration(self.settings.retrieval_config_path)
        active_generation = load_generation_configuration(self.settings.generation_config_path)
        model_rows: list[dict[str, Any]] = [
            {
                "stage": "evidence_search",
                "role": "Question understanding and passage matching",
                "active_model": active_retrieval.embedding_model,
                "evaluated_model": manifest.embedding_model,
                "matches": active_retrieval.embedding_model == manifest.embedding_model,
            },
            {
                "stage": "answer_generation",
                "role": "Grounded answer drafting",
                "active_model": self.settings.openai_chat_model,
                "evaluated_model": generation_artifact.generation_model,
                "matches": self.settings.openai_chat_model == generation_artifact.generation_model,
                "active_prompt": active_generation.promoted_prompt_id,
                "evaluated_prompt": generation_artifact.selected_prompt_id,
            },
            {
                "stage": "answer_judging",
                "role": "Automated evaluation with LLM-as-a-judge",
                "active_model": None,
                "evaluated_model": generation_artifact.judge_model,
                "matches": None,
            },
        ]

        selected_questions = selected_retrieval["questions"]
        selected_buckets = _rank_buckets(selected_questions)
        labels = Counter(
            result.judge.label
            for result in by_prompt.get(selected_prompt or "", {}).values()
            if result.judge is not None
        )
        return EvaluationOverview(
            benchmark={
                "question_count": len(cases),
                "finished_at": generation_artifact.finished_at,
                "human_reviewed": manifest.review_status == "reviewed",
            },
            retrieval={
                "selected_strategy": retrieval_result.selected_default["strategy"],
                "selected_configuration_id": configuration_id(retrieval_result.selected_default),
                "hit_count": sum(float(q["reciprocal_rank"]) > 0 for q in selected_questions),
                "question_count": len(selected_questions),
                "hit_rate": selected_retrieval["hit_rate"],
                "mrr": selected_retrieval["mrr"],
                "median_latency_ms": selected_retrieval["median_latency_ms"],
                "rank_buckets": selected_buckets,
                "baselines": baseline_rows,
            },
            generation={
                "selected_prompt_id": generation_artifact.selected_prompt_id,
                "promoted_prompt_id": generation_summary.promoted_prompt_id,
                "question_count": len(generation_cases),
                "relevant_count": labels["RELEVANT"],
                "partly_relevant_count": labels["PARTLY_RELEVANT"],
                "non_relevant_count": labels["NON_RELEVANT"],
                "valid_citation_handles": prompt["valid_citation_handles"] if prompt else 0,
                "citation_handles": prompt["citation_handles"] if prompt else 0,
                "median_latency_ms": prompt["median_latency_ms"] if prompt else None,
                "generation_cost_per_answer_usd": (
                    prompt["generation_cost_per_answer_usd"] if prompt else None
                ),
                "failures": prompt["failures"] if prompt else 0,
            },
            models=model_rows,
            example=example,
            warnings=[*retrieval_summary.warnings, *generation_summary.warnings],
        )
