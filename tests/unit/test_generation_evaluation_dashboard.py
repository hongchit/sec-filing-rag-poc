from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sec_filing_rag.core.config import Settings
from sec_filing_rag.evaluation.generation_dashboard import GenerationEvaluationDashboardService

ROOT = Path(__file__).resolve().parents[2]


class MissingDatabase:
    @contextmanager
    def transaction(self):  # type: ignore[no-untyped-def]
        raise RuntimeError("database data is unavailable")
        yield


def service() -> GenerationEvaluationDashboardService:
    settings = Settings(
        ingestion_api_token="0123456789abcdef",
        edgar_identity="Test test@example.com",
        openai_api_key="key",
        retrieval_evaluation_dataset_path=ROOT / "evaluation/retrieval-v1.jsonl",
        retrieval_evaluation_manifest_path=ROOT / "evaluation/retrieval-v1-manifest.json",
        generation_evaluation_result_path=ROOT / "evaluation/results/generation-v1.json",
        generation_config_path=ROOT / "config/generation.json",
    )
    return GenerationEvaluationDashboardService(MissingDatabase(), settings)  # type: ignore[arg-type]


def test_artifact_summary_remains_available_without_database_data() -> None:
    summary = service().summary()

    assert summary.selected_prompt_id == "basic-grounded-v2"
    assert summary.availability == {
        "artifact_loaded": True,
        "audit_record_available": False,
        "evidence_available": False,
    }
    assert {warning["code"] for warning in summary.warnings} == {
        "audit_record_unavailable",
        "evidence_unavailable",
    }
    winner = next(prompt for prompt in summary.prompts if prompt["selected"])
    assert winner["relevant_count"] == 95
    assert winner["generation_cost_per_answer_usd"] is not None


def test_matrix_and_answers_are_artifact_backed_when_evidence_is_missing() -> None:
    dashboard = service()
    cases = dashboard.cases()
    question = dashboard.question(cases.cases[0]["id"])

    assert len(cases.cases) == 96
    assert len(cases.cases[0]["results"]) == 5
    assert len(question.results) == 5
    assert question.evidence_available is False
    assert all(chunk["missing"] for chunk in [*question.expected, *question.retrieved])


def test_evaluated_prompt_source_requires_matching_hash() -> None:
    prompt = service().prompt("basic-grounded-v2")

    assert prompt.prompt_id == "basic-grounded-v2"
    assert "{question}" in prompt.source
