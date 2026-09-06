from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from sec_filing_rag.core.config import Settings
from sec_filing_rag.evaluation.dashboard import EvaluationDashboardService
from sec_filing_rag.evaluation.generation_dashboard import GenerationEvaluationDashboardService
from sec_filing_rag.evaluation.overview import EvaluationOverviewService

ROOT = Path(__file__).resolve().parents[2]


class Cursor:
    def __init__(self, row=None, rows=None):  # type: ignore[no-untyped-def]
        self.row, self.rows = row, rows or []

    def fetchone(self):  # type: ignore[no-untyped-def]
        return self.row

    def fetchall(self):  # type: ignore[no-untyped-def]
        return self.rows


class ArtifactDatabase:
    def __init__(self) -> None:
        artifact = json.loads(
            (ROOT / "evaluation/results/retrieval-v1.json").read_text(encoding="utf-8")
        )
        self.retrieval_run = {
            "id": artifact["evaluation_run_id"],
            "status": "succeeded",
            "dataset_sha256": artifact["dataset_sha256"],
            "configuration_sha256": artifact["configuration_sha256"],
            "started_at": "2026-08-31T00:00:00Z",
            "finished_at": "2026-08-31T00:01:00Z",
        }

    @contextmanager
    def transaction(self):  # type: ignore[no-untyped-def]
        database = self

        class Connection:
            def execute(self, query, _params):  # type: ignore[no-untyped-def]
                if "retrieval_evaluation_run" in query:
                    return Cursor(row=database.retrieval_run)
                return Cursor()

        yield Connection()


def test_public_overview_uses_validated_artifacts_and_named_models(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    candidate_counts: list[int] = []

    def choose(candidates):  # type: ignore[no-untyped-def]
        candidate_counts.append(len(candidates))
        return candidates[-1]

    monkeypatch.setattr("sec_filing_rag.evaluation.overview.secrets.choice", choose)
    settings = Settings(
        ingestion_api_token="0123456789abcdef",
        edgar_identity="Test test@example.com",
        openai_api_key="key",
        retrieval_config_path=ROOT / "config/retrieval.json",
        retrieval_evaluation_result_path=ROOT / "evaluation/results/retrieval-v1.json",
        retrieval_evaluation_dataset_path=ROOT / "evaluation/retrieval-v1.jsonl",
        retrieval_evaluation_manifest_path=ROOT / "evaluation/retrieval-v1-manifest.json",
        generation_config_path=ROOT / "config/generation.json",
        generation_evaluation_result_path=ROOT / "evaluation/results/generation-v1.json",
        model_pricing_config_path=ROOT / "config/model-pricing-v1.json",
    )
    database = ArtifactDatabase()
    overview = EvaluationOverviewService(
        EvaluationDashboardService(database, settings),  # type: ignore[arg-type]
        GenerationEvaluationDashboardService(database, settings),  # type: ignore[arg-type]
        settings,
    ).current()

    assert overview.benchmark["question_count"] == 96
    assert overview.retrieval["hit_count"] == 95
    assert overview.retrieval["rank_buckets"] == {
        "rank_one": 90,
        "rank_two_three": 5,
        "rank_four_ten": 0,
        "not_found": 1,
    }
    assert overview.retrieval["baselines"]["keyword"]["rank_buckets"]["rank_one"] == 88
    assert overview.generation["relevant_count"] == 95
    assert overview.example is not None and overview.example.consensus is True
    assert overview.example.judge_label == "RELEVANT"
    assert overview.example.interpretation
    assert overview.example.citations
    assert overview.example.accession
    assert overview.example.corpus_version_id
    assert candidate_counts and candidate_counts[0] > 1
    assert {row["evaluated_model"] for row in overview.models} == {
        "text-embedding-3-small",
        "gpt-5.4-mini",
    }
