from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from sec_filing_rag.core.config import Settings
from sec_filing_rag.evaluation.dashboard import (
    ArtifactConflict,
    EvaluationDashboardService,
    configuration_id,
    preview,
)

ROOT = Path(__file__).resolve().parents[2]


class EmptyDatabase:
    @contextmanager
    def transaction(self):  # type: ignore[no-untyped-def]
        raise AssertionError("database should not be reached for invalid artifacts")
        yield


class MissingDatabase:
    @contextmanager
    def transaction(self):  # type: ignore[no-untyped-def]
        raise RuntimeError("database data is unavailable")
        yield


class ConflictingDatabase:
    @contextmanager
    def transaction(self):  # type: ignore[no-untyped-def]
        class Cursor:
            def fetchone(self):  # type: ignore[no-untyped-def]
                return {
                    "id": "690954c1-d6e4-4d01-9981-f14d04708ae3",
                    "status": "succeeded",
                    "dataset_sha256": "0" * 64,
                    "configuration_sha256": "1" * 64,
                    "started_at": None,
                    "finished_at": None,
                }

        class Connection:
            def execute(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
                return Cursor()

        yield Connection()


def settings(tmp_path: Path, dataset: Path, manifest: Path, result: Path) -> Settings:
    return Settings(
        ingestion_api_token="0123456789abcdef",
        edgar_identity="Test test@example.com",
        openai_api_key="key",
        retrieval_evaluation_dataset_path=dataset,
        retrieval_evaluation_manifest_path=manifest,
        retrieval_evaluation_result_path=result,
    )


def test_configuration_ids_are_stable_and_preview_is_normalized() -> None:
    first = {"strategy": "rrf", "top_k": 5, "candidate_count": 10, "rrf_k": 60, "alpha": 0.5}
    second = dict(reversed(list(first.items())))
    assert configuration_id(first) == configuration_id(second)
    assert configuration_id(first).startswith("cfg-")
    assert preview("  First\n\n second\tthird  ") == "First second third"
    assert preview("x" * 300).endswith("…")


def test_checksum_conflict_is_rejected_before_database_access(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text("{}\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps(
            {
                "evaluation_run_id": "run",
                "dataset_sha256": "0" * 64,
                "configuration_sha256": "1" * 64,
                "results": [],
                "selected_default": {},
            }
        ),
        encoding="utf-8",
    )
    service = EvaluationDashboardService(
        EmptyDatabase(), settings(tmp_path, dataset, manifest, result)
    )  # type: ignore[arg-type]
    with pytest.raises(ArtifactConflict, match="malformed"):
        service.summary()


def artifact_service(database: object) -> EvaluationDashboardService:
    return EvaluationDashboardService(  # type: ignore[arg-type]
        database,
        Settings(
            ingestion_api_token="0123456789abcdef",
            edgar_identity="Test test@example.com",
            openai_api_key="key",
            retrieval_evaluation_dataset_path=ROOT / "evaluation/retrieval-v1.jsonl",
            retrieval_evaluation_manifest_path=ROOT / "evaluation/retrieval-v1-manifest.json",
            retrieval_evaluation_result_path=ROOT / "evaluation/results/retrieval-v1.json",
        ),
    )


def test_artifact_summary_and_cases_remain_available_without_database_data() -> None:
    dashboard = artifact_service(MissingDatabase())
    summary = dashboard.summary()
    cases = dashboard.cases(summary.selected_default_id)

    assert summary.run["status"] == "succeeded"
    assert summary.run["question_count"] == 96
    assert summary.availability == {
        "artifact_loaded": True,
        "audit_record_available": False,
        "evidence_available": False,
    }
    assert {warning["code"] for warning in summary.warnings} == {
        "audit_record_unavailable",
        "evidence_unavailable",
    }
    assert len(cases.cases) == 96
    assert all(chunk["missing"] for case in cases.cases for chunk in case["expected"])
    assert cases.warnings[0]["code"] == "evidence_unavailable"


def test_existing_conflicting_audit_record_remains_a_hard_error() -> None:
    with pytest.raises(ArtifactConflict, match="identity is inconsistent"):
        artifact_service(ConflictingDatabase()).summary()
