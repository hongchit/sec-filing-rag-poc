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


class EmptyDatabase:
    @contextmanager
    def transaction(self):  # type: ignore[no-untyped-def]
        raise AssertionError("database should not be reached for invalid artifacts")
        yield


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
