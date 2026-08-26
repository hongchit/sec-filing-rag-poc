from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from typing import Any

from sec_filing_rag.generation.service import AnswerParagraph, GeneratedAnswer
from sec_filing_rag.repositories.research import ResearchRepository
from sec_filing_rag.retrieval.service import RetrievalResult


class RecordingCursor:
    def fetchone(self) -> dict[str, Any] | None:
        return None


class RecordingConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, statement: str, params: tuple[Any, ...]) -> RecordingCursor:
        self.calls.append((statement, params))
        return RecordingCursor()


class RecordingDatabase:
    def __init__(self) -> None:
        self.connection = RecordingConnection()

    @contextmanager
    def transaction(self):  # type: ignore[no-untyped-def]
        yield self.connection


def test_save_evidence_serializes_provenance_as_json_text() -> None:
    database = RecordingDatabase()
    repository = ResearchRepository(database)  # type: ignore[arg-type]
    provenance = {
        "source": "10-K",
        "offsets": {"start": 12, "end": 34},
        "verified": True,
    }
    evidence = RetrievalResult(
        chunk_id="a" * 64,
        ticker="AAPL",
        accession="0000320193-25-000079",
        item="1",
        rank=1,
        strategy="keyword",
        score=0.75,
        text="Evidence text",
        citation_handle="AAPL-2025-1-001",
        provenance=provenance,
    )

    repository.save_evidence(uuid.uuid4(), [evidence])

    bound_provenance = database.connection.calls[0][1][-1]
    assert isinstance(bound_provenance, str)
    assert json.loads(bound_provenance) == provenance


def test_succeed_serializes_answer_and_limitations_as_json_text(monkeypatch: Any) -> None:
    database = RecordingDatabase()
    repository = ResearchRepository(database)  # type: ignore[arg-type]
    research_id = uuid.uuid4()
    answer = GeneratedAnswer(
        paragraphs=[
            AnswerParagraph(
                text="The company depends on its supplier network.",
                kind="filing_fact",
                citations=["AAPL-2025-1-001"],
            )
        ],
        limitations=["The filing does not quantify the dependency."],
        insufficient_evidence=False,
    )
    monkeypatch.setattr(repository, "get", lambda value: {"research_id": value})

    repository.succeed(research_id, answer)

    _, result_params = database.connection.calls[1]
    bound_answer = result_params[1]
    bound_limitations = result_params[3]
    assert isinstance(bound_answer, str)
    assert isinstance(bound_limitations, str)
    assert json.loads(bound_answer) == [item.model_dump(mode="json") for item in answer.paragraphs]
    assert json.loads(bound_limitations) == answer.limitations
