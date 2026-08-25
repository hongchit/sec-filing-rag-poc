from __future__ import annotations

import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from sec_filing_rag.ground_truth.service import (
    CorpusSnapshot,
    GeneratedQuestion,
    GenerationConfiguration,
    LLMChunkAssessment,
    deterministic_rank,
    generate_bundle,
    stable_question_id,
)


def row(chunk_id: str) -> dict[str, object]:
    return {"ticker": "AAPL", "item": "1", "chunk_id": chunk_id}


def test_sampling_is_seeded_stable_and_independent_of_input_order() -> None:
    rows = [row("a" * 64), row("b" * 64), row("c" * 64)]
    first = [value["chunk_id"] for value in deterministic_rank(rows, 42)]
    assert first == [value["chunk_id"] for value in deterministic_rank(list(reversed(rows)), 42)]
    assert first != [value["chunk_id"] for value in deterministic_rank(rows, 43)]


def test_structured_output_requires_one_exact_and_two_semantic_questions() -> None:
    exact = GeneratedQuestion(
        question="What was revenue?", goal="management_analysis", query_type="exact_keyword"
    )
    semantic1 = GeneratedQuestion(
        question="How did sales develop?",
        goal="management_analysis",
        query_type="semantic_paraphrase",
    )
    semantic2 = GeneratedQuestion(
        question="What explains the top-line change?",
        goal="management_analysis",
        query_type="semantic_paraphrase",
    )
    assert LLMChunkAssessment(
        meaningful=True,
        explanation="Useful financial discussion.",
        questions=[exact, semantic1, semantic2],
    ).meaningful
    assert (
        LLMChunkAssessment(
            meaningful=False, explanation="Navigation debris.", questions=[]
        ).questions
        == []
    )
    with pytest.raises(ValidationError, match="one exact and two semantic"):
        LLMChunkAssessment(
            meaningful=True, explanation="Useful.", questions=[exact, exact, semantic1]
        )


def test_question_validation_and_stable_id() -> None:
    question = GeneratedQuestion(
        question="Which products generate revenue?", goal="business", query_type="exact_keyword"
    )
    assert stable_question_id("a" * 64, question) == stable_question_id("a" * 64, question)
    with pytest.raises(ValidationError, match="prohibited"):
        GeneratedQuestion(
            question="What does the chunk say?", goal="business", query_type="exact_keyword"
        )
    with pytest.raises(ValidationError, match="question mark"):
        GeneratedQuestion(question="Describe revenue", goal="business", query_type="exact_keyword")


def test_generation_configuration_bounds_workers_and_candidates() -> None:
    values = {
        "version": "v1",
        "model": "gpt-5.4-mini",
        "prompt_version": "p1",
        "sampling_seed": 1,
        "workers": 6,
        "chunks_per_stratum": 2,
        "questions_per_chunk": 3,
        "max_candidates_per_stratum": 5,
    }
    assert GenerationConfiguration(**values).workers == 6
    with pytest.raises(ValidationError):
        GenerationConfiguration(**{**values, "workers": 7})
    with pytest.raises(ValidationError, match="maximum candidates"):
        GenerationConfiguration(**{**values, "max_candidates_per_stratum": 1})


def test_partial_generation_records_empty_and_rejected_strata_and_caps_screening() -> None:
    class Repository:
        def __init__(self) -> None:
            self.finished: dict[str, object] = {}

        def start_run(self, *args: object) -> None:
            pass

        def finish_run(self, *args: object, **kwargs: object) -> None:
            self.finished = kwargs

        def snapshot(self):  # type: ignore[no-untyped-def]
            corpora = [
                CorpusSnapshot(
                    ticker=ticker,
                    company=ticker,
                    corpus_version_id=uuid.uuid4(),
                    accession=f"{ticker}-2025",
                    report_date=date(2025, 9, 30),
                    source_url="https://example.test/filing",
                    parser_version="p",
                    chunking_version="c",
                    embedding_model="e",
                    embedding_dimensions=3,
                )
                for ticker in ("AAPL", "MSFT", "NVDA")
            ]
            rows = [
                {"ticker": "AAPL", "item": "1", "chunk_id": f"{index:064x}"} for index in range(6)
            ]
            return corpora, rows

    class RejectingAssessor:
        def __init__(self) -> None:
            self.calls = 0

        def assess(self, row: dict[str, object], run_id: uuid.UUID) -> LLMChunkAssessment:
            self.calls += 1
            return LLMChunkAssessment(meaningful=False, explanation="Not useful.", questions=[])

    repository, assessor = Repository(), RejectingAssessor()
    config = GenerationConfiguration(
        version="v1",
        prompt_version="p1",
        sampling_seed=7,
        workers=1,
        chunks_per_stratum=2,
        questions_per_chunk=3,
        max_candidates_per_stratum=5,
    )
    bundle = generate_bundle(repository, assessor, config, "a" * 64)  # type: ignore[arg-type]
    aapl_business = next(
        summary
        for summary in bundle.generation_summary
        if (summary.ticker, summary.item) == ("AAPL", "1")
    )
    empty = next(
        summary
        for summary in bundle.generation_summary
        if (summary.ticker, summary.item) == ("MSFT", "1A")
    )
    assert assessor.calls == 5
    assert (aapl_business.available_chunks, aapl_business.screened_chunks) == (6, 5)
    assert aapl_business.meaningfulness_shortfall and not aapl_business.source_shortfall
    assert empty.available_chunks == empty.screened_chunks == empty.selected_meaningful_chunks == 0
    assert empty.source_shortfall and empty.meaningfulness_shortfall
    assert bundle.chunks == []
    assert "error" not in repository.finished
