from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..domain.filings import safe_error
from ..generation.service import (
    GOAL_INSTRUCTIONS,
    GeneratedAnswer,
    GenerationConfiguration,
    ProviderUsage,
    build_context,
    validate_answer,
)
from ..retrieval.service import RetrievalQuery, RetrievalResult, RetrievalService
from .service import CorpusManifest, EvaluationCase, dataset_sha256

COURSE_COMMIT = "bc7b6aad6b92a5611d3d37bf7521a363f3b9d398"
JudgeLabel = Literal["RELEVANT", "PARTLY_RELEVANT", "NON_RELEVANT"]
LABEL_SCORE: dict[JudgeLabel, int] = {"RELEVANT": 2, "PARTLY_RELEVANT": 1, "NON_RELEVANT": 0}


@dataclass(frozen=True)
class GenerationEvaluationProgress:
    stage: str
    elapsed_seconds: float
    run_id: uuid.UUID | None = None
    status: str | None = None
    case_id: str | None = None
    ticker: str | None = None
    case_number: int | None = None
    case_count: int | None = None
    prompt_id: str | None = None
    prompt_number: int | None = None
    prompt_count: int | None = None
    attempt: int | None = None
    max_attempts: int | None = None
    completed_prompt_cases: int = 0
    total_prompt_cases: int = 0
    failure_count: int = 0
    selected_prompt_id: str | None = None


ProgressCallback = Callable[[GenerationEvaluationProgress], None]


def emit_generation_evaluation_progress(
    callback: ProgressCallback | None, event: GenerationEvaluationProgress
) -> None:
    """Report progress without allowing an observer failure to affect the evaluation."""
    if callback is None:
        return
    try:
        callback(event)
    except Exception:
        pass


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JudgeResult(StrictModel):
    label: JudgeLabel
    explanation: str = Field(min_length=1, max_length=2000)


class CitationAudit(StrictModel):
    citation_handles: int = Field(ge=0)
    valid_citation_handles: int = Field(ge=0)
    invalid_handles: list[str] = Field(default_factory=list)
    cross_corpus_citations: int = Field(ge=0)


class UsageRecord(StrictModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class CaseResult(StrictModel):
    case_id: str
    ticker: str
    accession: str
    corpus_version_id: uuid.UUID
    retrieved_chunk_ids: list[str]
    answer: GeneratedAnswer | None = None
    citation_audit: CitationAudit
    judge: JudgeResult | None = None
    generation_latency_ms: int | None = Field(default=None, ge=0)
    generation_usage: UsageRecord | None = None
    judge_usage: UsageRecord | None = None
    failure: str | None = Field(default=None, max_length=500)


class PromptEvaluation(StrictModel):
    prompt_id: str
    prompt_sha256: str = Field(default="0" * 64, pattern=r"^[0-9a-f]{64}$")
    cases: list[CaseResult] = Field(default_factory=list)
    labels: list[JudgeLabel] = Field(default_factory=list)
    valid_citation_handles: int = Field(ge=0)
    citation_handles: int = Field(ge=0)
    cross_corpus_citations: int = Field(ge=0)
    failures: int = Field(ge=0)
    generation_latencies_ms: list[int]
    eligible: bool | None = None
    mean_score: float | None = None
    relevant_count: int | None = None

    @model_validator(mode="after")
    def consistent(self) -> PromptEvaluation:
        if any(value < 0 for value in self.generation_latencies_ms):
            raise ValueError("latencies must be nonnegative")
        calculated_eligible = (
            self.failures == 0
            and bool(self.labels)
            and self.valid_citation_handles == self.citation_handles
            and self.cross_corpus_citations == 0
        )
        calculated_mean = (
            sum(LABEL_SCORE[label] for label in self.labels) / len(self.labels)
            if self.labels
            else 0.0
        )
        calculated_relevant = self.labels.count("RELEVANT")
        for name, supplied, calculated in (
            ("eligible", self.eligible, calculated_eligible),
            ("mean_score", self.mean_score, calculated_mean),
            ("relevant_count", self.relevant_count, calculated_relevant),
        ):
            if supplied is not None and supplied != calculated:
                raise ValueError(f"{name} is inconsistent with prompt results")
            setattr(self, name, calculated)
        return self

    @property
    def median_latency(self) -> float:
        return (
            median(self.generation_latencies_ms) if self.generation_latencies_ms else float("inf")
        )


def select_generation_winner(rows: list[PromptEvaluation]) -> PromptEvaluation:
    eligible = [row for row in rows if row.eligible]
    if not eligible:
        raise ValueError("no prompt is eligible for selection")
    return sorted(
        eligible,
        key=lambda row: (
            -float(row.mean_score or 0),
            -int(row.relevant_count or 0),
            row.median_latency,
            row.prompt_id,
        ),
    )[0]


class GenerationArtifact(StrictModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["generation-evaluation-v1"] = "generation-evaluation-v1"
    evaluation_run_id: uuid.UUID
    status: Literal["succeeded", "failed"]
    started_at: datetime
    finished_at: datetime
    course_commit: Literal["bc7b6aad6b92a5611d3d37bf7521a363f3b9d398"] = (
        "bc7b6aad6b92a5611d3d37bf7521a363f3b9d398"
    )
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieval_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    judge_rubric_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_model: str
    judge_model: str
    pricing_snapshot: dict[str, Any]
    case_ids: list[str]
    prompts: list[PromptEvaluation]
    selected_prompt_id: str | None
    selection_rationale: dict[str, Any]
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def cross_fields(self) -> GenerationArtifact:
        if self.finished_at < self.started_at or len(self.case_ids) != len(set(self.case_ids)):
            raise ValueError("invalid timestamps or duplicate case IDs")
        if len({row.prompt_id for row in self.prompts}) != len(self.prompts):
            raise ValueError("prompt IDs must be unique")
        expected = set(self.case_ids)
        for prompt in self.prompts:
            ids = [case.case_id for case in prompt.cases]
            if prompt.cases and (len(ids) != len(set(ids)) or set(ids) != expected):
                raise ValueError(f"{prompt.prompt_id} has incomplete or duplicate case coverage")
            if prompt.cases:
                labels = [case.judge.label for case in prompt.cases if case.judge]
                failures = sum(
                    case.failure is not None or case.judge is None for case in prompt.cases
                )
                audits = [case.citation_audit for case in prompt.cases]
                if (
                    labels != prompt.labels
                    or failures != prompt.failures
                    or sum(a.citation_handles for a in audits) != prompt.citation_handles
                    or sum(a.valid_citation_handles for a in audits)
                    != prompt.valid_citation_handles
                    or sum(a.cross_corpus_citations for a in audits)
                    != prompt.cross_corpus_citations
                ):
                    raise ValueError(f"{prompt.prompt_id} aggregate is inconsistent with cases")
        eligible = [row for row in self.prompts if row.eligible]
        if eligible and self.selected_prompt_id != select_generation_winner(self.prompts).prompt_id:
            raise ValueError("selected prompt does not match deterministic winner")
        if not eligible and self.selected_prompt_id is not None:
            raise ValueError("selected prompt must be null when no prompt is eligible")
        return self


def load_generation_artifact(path: Path) -> GenerationArtifact:
    return GenerationArtifact.model_validate_json(path.read_text(encoding="utf-8"))


def validate_artifact_inputs(
    artifact: GenerationArtifact,
    cases: list[EvaluationCase],
    dataset: Path,
    manifest: CorpusManifest,
) -> None:
    if artifact.dataset_sha256 != dataset_sha256(dataset):
        raise ValueError("artifact dataset checksum does not match selected dataset")
    if artifact.corpus_snapshot_sha256 != manifest.corpus_snapshot_sha256:
        raise ValueError("artifact corpus snapshot does not match selected manifest")
    if artifact.case_ids != [case.id for case in cases]:
        raise ValueError("artifact case order or coverage does not match selected dataset")


def artifact_markdown(artifact: GenerationArtifact) -> str:
    rows = [
        "# Generation evaluation",
        "",
        f"- Status: `{artifact.status}`",
        f"- Cases: `{len(artifact.case_ids)}`",
        "",
        "| Prompt | Mean | Relevant | Failures | Eligible |",
        "|---|---:|---:|---:|:---:|",
    ]
    for prompt in artifact.prompts:
        rows.append(
            f"| `{prompt.prompt_id}` | {float(prompt.mean_score or 0):.4f} | {prompt.relevant_count} | {prompt.failures} | {'yes' if prompt.eligible else 'no'} |"
        )
    rows.extend(["", f"Selected prompt: `{artifact.selected_prompt_id or 'none'}`", ""])
    return "\n".join(rows)


class AnswerProvider(Protocol):
    def generate(self, *, model: str, prompt: str) -> tuple[GeneratedAnswer, ProviderUsage]: ...


class JudgeProvider(Protocol):
    def judge(self, *, model: str, prompt: str) -> tuple[JudgeResult, ProviderUsage]: ...


class EvaluationRepository(Protocol):
    def create_run(self, **values: Any) -> uuid.UUID: ...
    def reference_chunks(self, case: EvaluationCase) -> list[RetrievalResult]: ...
    def usage(self, run_id: uuid.UUID, **values: Any) -> None: ...
    def finish(self, run_id: uuid.UUID, **values: Any) -> None: ...


def citation_audit(
    answer: GeneratedAnswer, evidence: list[RetrievalResult], *, ticker: str, accession: str
) -> CitationAudit:
    handles = [handle for paragraph in answer.paragraphs for handle in paragraph.citations]
    allowed = {item.citation_handle: item for item in evidence}
    invalid_occurrences = [handle for handle in handles if handle not in allowed]
    cross = sum(
        1
        for handle in handles
        if handle in allowed
        and (allowed[handle].ticker != ticker or allowed[handle].accession != accession)
    )
    return CitationAudit(
        citation_handles=len(handles),
        valid_citation_handles=len(handles) - len(invalid_occurrences),
        invalid_handles=sorted(set(invalid_occurrences)),
        cross_corpus_citations=cross,
    )


class GenerationEvaluationRunner:
    def __init__(
        self,
        repository: EvaluationRepository,
        retrieval: RetrievalService,
        answer_provider: AnswerProvider,
        judge_provider: JudgeProvider,
        generation_config: GenerationConfiguration,
        *,
        generation_model: str,
        judge_model: str,
        judge_rubric: str,
        pricing_snapshot: dict[str, Any],
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.repository, self.retrieval = repository, retrieval
        self.answer_provider, self.judge_provider = answer_provider, judge_provider
        self.config, self.generation_model, self.judge_model = (
            generation_config,
            generation_model,
            judge_model,
        )
        self.judge_rubric, self.pricing_snapshot = judge_rubric, pricing_snapshot
        self.progress_callback = progress_callback

    def workload(self, cases: list[EvaluationCase], prompt_ids: list[str]) -> dict[str, int]:
        vector = (
            self.retrieval.config.default is not None
            and self.retrieval.config.default.strategy != "keyword"
        )
        return {
            "cases": len(cases),
            "prompts": len(prompt_ids),
            "embedding_calls": len(cases) if vector else 0,
            "generation_calls": len(cases) * len(prompt_ids),
            "judge_calls": len(cases) * len(prompt_ids),
        }

    def run(
        self,
        cases: list[EvaluationCase],
        prompt_ids: list[str],
        *,
        dataset_hash: str,
        corpus_hash: str,
    ) -> GenerationArtifact:
        default = self.retrieval.config.default
        if default is None:
            raise ValueError("a promoted retrieval configuration is required")
        templates = {prompt_id: self.config.prompt(prompt_id) for prompt_id in prompt_ids}
        started_at = datetime.now(UTC)
        progress_started = time.monotonic()
        total_prompt_cases = len(cases) * len(prompt_ids)
        completed_prompt_cases = 0
        failure_count = 0
        run_id = self.repository.create_run(
            dataset_sha256=dataset_hash,
            corpus_snapshot_sha256=corpus_hash,
            retrieval_configuration_sha256=self.retrieval.config.sha256(),
            generation_configuration_sha256=self.config.sha256(),
            chat_model=self.generation_model,
            judge_model=self.judge_model,
            pricing_snapshot=self.pricing_snapshot,
        )

        def progress(stage: str, **values: Any) -> None:
            emit_generation_evaluation_progress(
                self.progress_callback,
                GenerationEvaluationProgress(
                    stage=stage,
                    elapsed_seconds=time.monotonic() - progress_started,
                    run_id=run_id,
                    completed_prompt_cases=completed_prompt_cases,
                    total_prompt_cases=total_prompt_cases,
                    failure_count=min(failure_count, 100),
                    **values,
                ),
            )

        workload_values = {"case_count": len(cases), "prompt_count": len(prompt_ids)}
        progress("audited_run_created", **workload_values)
        progress("workload_ready", **workload_values)
        results: dict[str, list[CaseResult]] = {prompt_id: [] for prompt_id in prompt_ids}
        errors: list[str] = []
        try:
            for case_number, case in enumerate(cases, 1):
                case_values = {
                    "case_id": case.id,
                    "ticker": case.ticker,
                    "case_number": case_number,
                    "case_count": len(cases),
                }
                progress("retrieval_started", **case_values)
                query = RetrievalQuery(
                    question=case.question,
                    ticker=case.ticker,
                    corpus_version_id=case.corpus_version_id,
                    allowed_items=case.allowed_items,
                    strategy=default.strategy,
                    candidate_count=default.candidate_count,
                    top_k=default.top_k,
                    alpha=default.alpha or 0.5,
                    rrf_k=default.rrf_k or 60,
                )
                try:
                    retrieved = self.retrieval.retrieve(query, generation_evaluation_run_id=run_id)
                except Exception:
                    progress("retrieval_failed", **case_values)
                    raise
                progress("retrieval_completed", **case_values)
                context, evidence = build_context(retrieved, self.config.context_max_chars)
                references = self.repository.reference_chunks(case)
                for prompt_number, prompt_id in enumerate(prompt_ids, 1):
                    prompt_values = {
                        **case_values,
                        "prompt_id": prompt_id,
                        "prompt_number": prompt_number,
                        "prompt_count": len(prompt_ids),
                    }
                    template, _ = templates[prompt_id]
                    chunk_ids = [item.chunk_id for item in evidence]
                    goal_instruction = (
                        GOAL_INSTRUCTIONS["legal_regulatory_risk"]
                        if case.goal == "legal_and_regulatory_risk"
                        else GOAL_INSTRUCTIONS[case.goal]
                    )
                    prompt = template.format(
                        goal_instruction=goal_instruction,
                        question=case.question,
                        context=context,
                    )
                    answer: GeneratedAnswer | None = None
                    audit = CitationAudit(
                        citation_handles=0,
                        valid_citation_handles=0,
                        cross_corpus_citations=0,
                    )
                    latency = 0
                    usage = ProviderUsage(None, None, None)
                    generation_error: str | None = None
                    for _attempt in range(1, self.config.max_retries + 2):
                        attempt_values = {
                            **prompt_values,
                            "attempt": _attempt,
                            "max_attempts": self.config.max_retries + 1,
                        }
                        progress("generation_started", **attempt_values)
                        started = time.monotonic()
                        try:
                            answer, usage = self.answer_provider.generate(
                                model=self.generation_model, prompt=prompt
                            )
                            latency = int((time.monotonic() - started) * 1000)
                            audit = citation_audit(
                                answer, evidence, ticker=case.ticker, accession=case.accession
                            )
                            validate_answer(
                                answer,
                                evidence,
                                self.config,
                                ticker=case.ticker,
                                accession=case.accession,
                            )
                            self.repository.usage(
                                run_id,
                                operation="answer_generation",
                                model=self.generation_model,
                                usage=usage,
                                latency_ms=latency,
                                attempt=_attempt,
                                outcome="succeeded",
                            )
                            generation_error = None
                            progress("generation_completed", **attempt_values)
                            break
                        except Exception as exc:
                            generation_error = safe_error(exc)[:500]
                            self.repository.usage(
                                run_id,
                                operation="answer_generation",
                                model=self.generation_model,
                                usage=usage,
                                latency_ms=int((time.monotonic() - started) * 1000),
                                attempt=_attempt,
                                outcome=generation_error,
                            )
                            progress("generation_retry_failed", **attempt_values)
                    if generation_error is not None or answer is None:
                        error = generation_error or "answer generation failed"
                        errors.append(f"{prompt_id}/{case.id}: {error}")
                        failure_count += 1
                        results[prompt_id].append(
                            CaseResult(
                                case_id=case.id,
                                ticker=case.ticker,
                                accession=case.accession,
                                corpus_version_id=case.corpus_version_id,
                                retrieved_chunk_ids=chunk_ids,
                                citation_audit=audit,
                                failure=error,
                            )
                        )
                        completed_prompt_cases += 1
                        progress("generation_failed", **prompt_values)
                        progress("prompt_case_completed", **prompt_values)
                        continue
                    try:
                        progress("judge_started", **prompt_values)
                        reference_text = "\n\n".join(item.text for item in references)
                        judge_prompt = self.judge_rubric.format(
                            question=case.question,
                            answer=answer.model_dump_json(),
                            reference_evidence=reference_text,
                        )
                        judge, judge_usage = self.judge_provider.judge(
                            model=self.judge_model, prompt=judge_prompt
                        )
                        self.repository.usage(
                            run_id,
                            operation="answer_judge",
                            model=self.judge_model,
                            usage=judge_usage,
                            latency_ms=0,
                            attempt=1,
                            outcome="succeeded",
                        )
                        progress("judge_completed", **prompt_values)
                        results[prompt_id].append(
                            CaseResult(
                                case_id=case.id,
                                ticker=case.ticker,
                                accession=case.accession,
                                corpus_version_id=case.corpus_version_id,
                                retrieved_chunk_ids=chunk_ids,
                                answer=answer,
                                citation_audit=audit,
                                judge=judge,
                                generation_latency_ms=latency,
                                generation_usage=UsageRecord(**usage.__dict__),
                                judge_usage=UsageRecord(**judge_usage.__dict__),
                            )
                        )
                    except Exception as exc:
                        error = safe_error(exc)[:500]
                        errors.append(f"{prompt_id}/{case.id}: {error}")
                        failure_count += 1
                        self.repository.usage(
                            run_id,
                            operation="answer_judge",
                            model=self.judge_model,
                            usage=ProviderUsage(None, None, None),
                            latency_ms=0,
                            attempt=1,
                            outcome=error,
                        )
                        results[prompt_id].append(
                            CaseResult(
                                case_id=case.id,
                                ticker=case.ticker,
                                accession=case.accession,
                                corpus_version_id=case.corpus_version_id,
                                retrieved_chunk_ids=chunk_ids,
                                answer=answer,
                                citation_audit=audit,
                                generation_latency_ms=latency,
                                generation_usage=UsageRecord(**usage.__dict__),
                                failure=error,
                            )
                        )
                        progress("judge_failed", **prompt_values)
                    completed_prompt_cases += 1
                    progress("prompt_case_completed", **prompt_values)
                progress("case_completed", **case_values)
            prompts = [
                self._aggregate(prompt_id, templates[prompt_id][1], results[prompt_id])
                for prompt_id in prompt_ids
            ]
            selected = (
                select_generation_winner(prompts).prompt_id
                if any(row.eligible for row in prompts)
                else None
            )
            progress("winner_selected", selected_prompt_id=selected)
            rationale = {
                "ordering": [
                    "mean_label_score_desc",
                    "relevant_count_desc",
                    "median_generation_latency_asc",
                    "prompt_id_asc",
                ],
                "selected_prompt_id": selected,
            }
            artifact = GenerationArtifact(
                evaluation_run_id=run_id,
                status="succeeded" if selected else "failed",
                started_at=started_at,
                finished_at=datetime.now(UTC),
                dataset_sha256=dataset_hash,
                corpus_snapshot_sha256=corpus_hash,
                retrieval_configuration_sha256=self.retrieval.config.sha256(),
                generation_configuration_sha256=self.config.sha256(),
                judge_rubric_sha256=_sha256(self.judge_rubric),
                generation_model=self.generation_model,
                judge_model=self.judge_model,
                pricing_snapshot=self.pricing_snapshot,
                case_ids=[case.id for case in cases],
                prompts=prompts,
                selected_prompt_id=selected,
                selection_rationale=rationale,
                errors=errors[:100],
            )
            self.repository.finish(
                run_id,
                status=artifact.status,
                selected_prompt_id=selected,
                selection_rationale=rationale,
                safe_error=None if selected else "no eligible prompt",
            )
            progress(
                "run_finished",
                status=artifact.status,
                selected_prompt_id=selected,
            )
            return artifact
        except Exception as exc:
            self.repository.finish(
                run_id,
                status="failed",
                selected_prompt_id=None,
                selection_rationale={},
                safe_error=safe_error(exc),
            )
            progress("run_finished", status="failed")
            raise

    @staticmethod
    def _aggregate(prompt_id: str, prompt_hash: str, cases: list[CaseResult]) -> PromptEvaluation:
        audits = [case.citation_audit for case in cases]
        return PromptEvaluation(
            prompt_id=prompt_id,
            prompt_sha256=prompt_hash,
            cases=cases,
            labels=[case.judge.label for case in cases if case.judge],
            valid_citation_handles=sum(a.valid_citation_handles for a in audits),
            citation_handles=sum(a.citation_handles for a in audits),
            cross_corpus_citations=sum(a.cross_corpus_citations for a in audits),
            failures=sum(case.failure is not None or case.judge is None for case in cases),
            generation_latencies_ms=[
                case.generation_latency_ms
                for case in cases
                if case.generation_latency_ms is not None
            ],
        )


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
