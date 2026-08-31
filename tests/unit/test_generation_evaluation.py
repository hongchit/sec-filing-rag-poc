from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from sec_filing_rag.cli.generation_evaluation import format_progress
from sec_filing_rag.evaluation.generation import (
    CaseResult,
    CitationAudit,
    GenerationArtifact,
    GenerationEvaluationProgress,
    JudgeResult,
    PromptEvaluation,
    citation_audit,
    emit_generation_evaluation_progress,
    select_generation_winner,
)
from sec_filing_rag.generation.service import AnswerParagraph, GeneratedAnswer
from sec_filing_rag.retrieval.service import RetrievalResult

HASH = "a" * 64


def test_progress_contract_is_immutable_and_reporter_failures_are_isolated() -> None:
    event = GenerationEvaluationProgress(stage="judging", elapsed_seconds=192.9)
    with pytest.raises(FrozenInstanceError):
        event.stage = "changed"  # type: ignore[misc]

    def broken_reporter(_event: GenerationEvaluationProgress) -> None:
        raise OSError("closed stream")

    emit_generation_evaluation_progress(broken_reporter, event)


def test_progress_format_contains_safe_operational_counters() -> None:
    run_id = uuid4()
    line = format_progress(
        GenerationEvaluationProgress(
            stage="judge_started",
            elapsed_seconds=192.9,
            run_id=run_id,
            case_id="gtq-0123456789abcdef",
            ticker="AAPL",
            case_number=8,
            case_count=96,
            prompt_id="basic-grounded-v2",
            prompt_number=3,
            prompt_count=5,
            attempt=2,
            max_attempts=3,
            completed_prompt_cases=37,
            total_prompt_cases=480,
            failure_count=1,
        )
    )
    assert line == (
        f"generation-evaluation · 00:03:12 · run {run_id} · case 8/96 AAPL · "
        "prompt 3/5 basic-grounded-v2 · attempt 2/3 · judge started · "
        "completed 37/480 · failures 1"
    )


def _prompt(
    prompt_id: str, label: str, latency: int = 10, *, failures: int = 0
) -> PromptEvaluation:
    return PromptEvaluation(
        prompt_id=prompt_id,
        labels=[label],
        valid_citation_handles=1,
        citation_handles=1,
        cross_corpus_citations=0,
        failures=failures,
        generation_latencies_ms=[latency],
    )


def test_winner_uses_quality_then_latency_then_stable_id() -> None:
    assert (
        select_generation_winner([_prompt("b", "RELEVANT"), _prompt("a", "RELEVANT")]).prompt_id
        == "a"
    )
    assert (
        select_generation_winner(
            [_prompt("fast", "RELEVANT", 1), _prompt("slow", "RELEVANT", 9)]
        ).prompt_id
        == "fast"
    )
    assert not _prompt("failed", "RELEVANT", failures=1).eligible


def test_citation_audit_reports_invalid_and_cross_corpus_handles() -> None:
    evidence = [
        RetrievalResult(HASH, "AAPL", "accession", "1", 1, "keyword", 1.0, "text", "valid", {})
    ]
    answer = GeneratedAnswer(
        paragraphs=[
            AnswerParagraph(text="answer", kind="filing_fact", citations=["valid", "invented"])
        ],
        limitations=[],
        insufficient_evidence=False,
    )
    audit = citation_audit(answer, evidence, ticker="MSFT", accession="other")
    assert audit.invalid_handles == ["invented"]
    assert audit.valid_citation_handles == 1
    assert audit.cross_corpus_citations == 1


def test_artifact_rejects_inconsistent_case_aggregates() -> None:
    case = CaseResult(
        case_id="case",
        ticker="AAPL",
        accession="accession",
        corpus_version_id=uuid4(),
        retrieved_chunk_ids=[],
        citation_audit=CitationAudit(
            citation_handles=0, valid_citation_handles=0, cross_corpus_citations=0
        ),
        judge=JudgeResult(label="RELEVANT", explanation="supported"),
    )
    prompt = PromptEvaluation(
        prompt_id="prompt",
        cases=[case],
        labels=["PARTLY_RELEVANT"],
        valid_citation_handles=0,
        citation_handles=0,
        cross_corpus_citations=0,
        failures=0,
        generation_latencies_ms=[],
    )
    with pytest.raises(ValidationError, match="aggregate is inconsistent"):
        GenerationArtifact(
            evaluation_run_id=uuid4(),
            status="succeeded",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            dataset_sha256=HASH,
            corpus_snapshot_sha256=HASH,
            retrieval_configuration_sha256=HASH,
            generation_configuration_sha256=HASH,
            judge_rubric_sha256=HASH,
            generation_model="generation",
            judge_model="judge",
            pricing_snapshot={},
            case_ids=["case"],
            prompts=[prompt],
            selected_prompt_id="prompt",
            selection_rationale={},
        )
