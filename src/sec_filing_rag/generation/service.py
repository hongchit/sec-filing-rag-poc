from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..core.pricing import PricingConfiguration
from ..domain.filings import SUPPORTED_ITEMS, safe_error, sha256_bytes
from ..retrieval.service import RetrievalQuery, RetrievalResult, RetrievalService

ROOT = Path(__file__).resolve().parents[3]
ResearchGoal = Literal[
    "business", "key_risks", "management_analysis", "market_risk", "legal_regulatory_risk"
]
ParagraphKind = Literal["filing_fact", "interpretation"]
Disposition = Literal["answered", "investment_advice", "out_of_scope"]

INVESTMENT_ADVICE_MESSAGE = (
    "This tool cannot answer requests for investment recommendations, trades, price targets, "
    "or price and return predictions. Ask a question about disclosures in the selected company's Form 10-K."
)
OUT_OF_SCOPE_MESSAGE = (
    "This tool answers questions grounded in the selected company's supported original Form 10-K items."
)

GOAL_INSTRUCTIONS: dict[ResearchGoal, str] = {
    "business": "Explain the company's business, products, customers, and operating model.",
    "key_risks": "Identify and synthesize the material risks disclosed by the company.",
    "management_analysis": "Analyze management's discussion of results, liquidity, and trends.",
    "market_risk": "Explain disclosed exposure to market risks and related controls.",
    "legal_regulatory_risk": "Explain disclosed legal and regulatory proceedings and risks.",
}


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str
    corpus_version_id: uuid.UUID
    goal: ResearchGoal
    question: str = Field(min_length=1, max_length=2000)
    allowed_items: frozenset[str] | None = None

    @field_validator("ticker")
    @classmethod
    def ticker_is_valid(cls, value: str) -> str:
        from ..core.config import TICKER_RE

        normalized = value.strip().upper()
        if not TICKER_RE.fullmatch(normalized):
            raise ValueError("invalid ticker")
        return normalized

    @field_validator("question")
    @classmethod
    def question_is_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value  # Preserve the submitted value byte-for-byte.

    @field_validator("allowed_items")
    @classmethod
    def items_are_supported(cls, value: frozenset[str] | None) -> frozenset[str] | None:
        if value is not None and (not value or not value <= SUPPORTED_ITEMS):
            raise ValueError("allowed_items must be a non-empty subset of supported Items")
        return value


class AnswerParagraph(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1)
    kind: ParagraphKind
    citations: list[str] = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("paragraph text must not be blank")
        return value

    @field_validator("citations")
    @classmethod
    def distinct_citations(cls, value: list[str]) -> list[str]:
        if any(not handle.strip() for handle in value) or len(value) != len(set(value)):
            raise ValueError("citations must be nonblank and unique")
        return value


class GeneratedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paragraphs: list[AnswerParagraph]
    limitations: list[str]
    insufficient_evidence: bool
    disposition: Disposition = "answered"
    policy_refusal: bool = False

    @model_validator(mode="after")
    def coherent_insufficiency(self) -> GeneratedAnswer:
        if self.disposition != "answered":
            if self.paragraphs or self.limitations or self.insufficient_evidence:
                raise ValueError("rejected dispositions cannot contain answer content")
            self.policy_refusal = self.disposition == "investment_advice"
            return self
        if self.insufficient_evidence and not self.limitations:
            raise ValueError("insufficient evidence requires a limitation")
        if self.policy_refusal:
            self.disposition = "investment_advice"
            self.paragraphs = []
            self.limitations = []
            self.insufficient_evidence = False
        return self


class PromptEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=100)
    path: Path


class GenerationConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    promoted_prompt_id: str | None
    promotion_reason: str | None = None
    context_max_chars: int = Field(gt=0)
    max_paragraphs: int = Field(ge=1, le=20)
    max_paragraph_chars: int = Field(ge=1, le=10000)
    max_limitations: int = Field(ge=0, le=10)
    max_limitation_chars: int = Field(ge=1, le=2000)
    max_retries: int = Field(ge=0, le=2)
    prompts: list[PromptEntry] = Field(min_length=2)

    @model_validator(mode="after")
    def promoted_prompt_exists(self) -> GenerationConfiguration:
        ids = [prompt.id for prompt in self.prompts]
        if len(ids) != len(set(ids)):
            raise ValueError("prompt IDs must be unique")
        if self.promoted_prompt_id is not None and self.promoted_prompt_id not in ids:
            raise ValueError("promoted prompt does not exist")
        return self

    def prompt(self, prompt_id: str) -> tuple[str, str]:
        entry = next((value for value in self.prompts if value.id == prompt_id), None)
        if entry is None:
            raise ValueError("unknown prompt")
        path = entry.path if entry.path.is_absolute() else ROOT / entry.path
        content = path.read_text(encoding="utf-8")
        return content, sha256_bytes(content.encode())

    def sha256(self) -> str:
        return sha256_bytes(self.model_dump_json(exclude_none=False).encode())


def load_generation_configuration(path: Path) -> GenerationConfiguration:
    return GenerationConfiguration.model_validate_json(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class ContextEvidence:
    result: RetrievalResult
    rendered: str


def build_context(
    results: list[RetrievalResult], max_chars: int = 30_000
) -> tuple[str, list[RetrievalResult]]:
    """Include complete evidence blocks in rank order, skipping blocks that do not fit."""
    blocks: list[str] = []
    selected: list[RetrievalResult] = []
    used = 0
    for result in sorted(results, key=lambda item: item.rank):
        metadata = json.dumps(
            {
                "citation_handle": result.citation_handle,
                "ticker": result.ticker,
                "accession": result.accession,
                "item": result.item,
                "chunk_id": result.chunk_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        block = f"<untrusted_evidence metadata='{metadata}'>\n{result.text}\n</untrusted_evidence>"
        separator = "\n\n" if blocks else ""
        if used + len(separator) + len(block) <= max_chars:
            blocks.append(block)
            selected.append(result)
            used += len(separator) + len(block)
    return "\n\n".join(blocks), selected


def deterministic_insufficient_answer() -> GeneratedAnswer:
    return GeneratedAnswer(
        paragraphs=[],
        limitations=["No filing evidence matched the submitted question and filters."],
        insufficient_evidence=True,
        policy_refusal=False,
    )


def validate_answer(
    answer: GeneratedAnswer,
    evidence: list[RetrievalResult],
    config: GenerationConfiguration,
    *,
    ticker: str,
    accession: str,
) -> None:
    if answer.disposition != "answered" and (
        answer.paragraphs or answer.limitations or answer.insufficient_evidence
    ):
        raise ValueError("rejected dispositions cannot contain answer content")
    if len(answer.paragraphs) > config.max_paragraphs:
        raise ValueError("too many answer paragraphs")
    if len(answer.limitations) > config.max_limitations:
        raise ValueError("too many limitations")
    if any(len(item.text) > config.max_paragraph_chars for item in answer.paragraphs):
        raise ValueError("answer paragraph exceeds maximum length")
    if any(
        not item.strip() or len(item) > config.max_limitation_chars for item in answer.limitations
    ):
        raise ValueError("invalid limitation")
    allowed = {item.citation_handle: item for item in evidence}
    for paragraph in answer.paragraphs:
        for handle in paragraph.citations:
            item = allowed.get(handle)
            if item is None:
                raise ValueError("answer contains citation outside retrieved context")
            if item.ticker != ticker or item.accession != accession:
                raise ValueError("answer contains cross-corpus citation")


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class AnswerProvider(Protocol):
    def generate(self, *, model: str, prompt: str) -> tuple[GeneratedAnswer, ProviderUsage]: ...


class OpenAIAnswerProvider:
    def __init__(self, client: Any) -> None:
        self.client = client

    def generate(self, *, model: str, prompt: str) -> tuple[GeneratedAnswer, ProviderUsage]:
        response = self.client.responses.parse(
            model=model, input=prompt, text_format=GeneratedAnswer
        )
        parsed = response.output_parsed
        if parsed is None:
            raise ValueError("provider refused or returned no structured answer")
        usage = getattr(response, "usage", None)
        return parsed, ProviderUsage(
            getattr(usage, "input_tokens", None),
            getattr(usage, "output_tokens", None),
            getattr(usage, "total_tokens", None),
        )


class ResearchRepository(Protocol):
    def create(
        self,
        request: ResearchRequest,
        *,
        prompt_id: str,
        model: str,
        idempotency_key: uuid.UUID | None = None,
        retrieval_configuration_sha256: str | None = None,
        generation_configuration_sha256: str | None = None,
        prompt_sha256: str | None = None,
        pricing_snapshot: dict[str, Any] | None = None,
    ) -> uuid.UUID: ...
    def idempotent_result(
        self, key: uuid.UUID, request: ResearchRequest
    ) -> dict[str, Any] | None: ...
    def identity(self, research_id: uuid.UUID) -> tuple[str, str]: ...
    def save_evidence(self, research_id: uuid.UUID, evidence: list[RetrievalResult]) -> None: ...
    def usage(self, research_id: uuid.UUID, **values: Any) -> None: ...
    def succeed(self, research_id: uuid.UUID, answer: GeneratedAnswer) -> dict[str, Any]: ...
    def fail(self, research_id: uuid.UUID, error: str) -> None: ...
    def get(self, research_id: uuid.UUID) -> dict[str, Any] | None: ...


class ResearchFailure(RuntimeError):
    def __init__(self, research_id: uuid.UUID) -> None:
        super().__init__("answer generation failed")
        self.research_id = research_id


class IdempotencyConflict(RuntimeError):
    pass


class ResearchInProgress(RuntimeError):
    def __init__(self, research_id: uuid.UUID) -> None:
        self.research_id = research_id


class ResearchService:
    def __init__(
        self,
        repository: ResearchRepository,
        retrieval: RetrievalService,
        provider: AnswerProvider,
        config: GenerationConfiguration,
        model: str,
        pricing: PricingConfiguration | None = None,
        embedding_model: str | None = None,
    ) -> None:
        self.repository = repository
        self.retrieval = retrieval
        self.provider = provider
        self.config = config
        self.model = model
        self.pricing = pricing
        self.embedding_model = embedding_model

    def create(
        self,
        request: ResearchRequest,
        *,
        idempotency_key: uuid.UUID | None = None,
        on_stage: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        prompt_id = self.config.promoted_prompt_id
        if prompt_id is None or self.retrieval.config.default is None:
            raise ValueError("runtime retrieval and prompt defaults must be configured")
        if idempotency_key is not None and hasattr(self.repository, "idempotent_result"):
            existing = self.repository.idempotent_result(idempotency_key, request)
            if existing is not None:
                return existing
        template, prompt_sha256 = self.config.prompt(prompt_id)
        try:
            snapshot = (
                self.pricing.snapshot(
                    embedding_model=self.embedding_model or self.retrieval.config.embedding_model,
                    chat_model=self.model,
                )
                if self.pricing is not None
                else None
            )
            research_id = self.repository.create(
                request,
                prompt_id=prompt_id,
                model=self.model,
                idempotency_key=idempotency_key,
                retrieval_configuration_sha256=self.retrieval.config.sha256(),
                generation_configuration_sha256=self.config.sha256(),
                prompt_sha256=prompt_sha256,
                pricing_snapshot=snapshot,
            )
        except TypeError:  # Compatibility for lightweight test repositories.
            research_id = self.repository.create(request, prompt_id=prompt_id, model=self.model)

        def stage(name: str, **payload: Any) -> None:
            if on_stage is None:
                return
            try:
                on_stage(name, {"research_id": str(research_id), **payload})
            except Exception:
                return

        try:
            default = self.retrieval.config.default
            query = RetrievalQuery(
                question=request.question,
                ticker=request.ticker,
                corpus_version_id=request.corpus_version_id,
                allowed_items=request.allowed_items,
                strategy=default.strategy,
                candidate_count=default.candidate_count,
                top_k=default.top_k,
                alpha=default.alpha or 0.5,
                rrf_k=default.rrf_k or 60,
            )
            stage("retrieving")
            results = self.retrieval.retrieve(query, research_id=research_id)
            context, evidence = build_context(results, self.config.context_max_chars)
            self.repository.save_evidence(research_id, evidence)
            stage("retrieved", evidence=[item.__dict__ for item in evidence])
            _, accession = self.repository.identity(research_id)
            stage("building_context")
            prompt = template.format(
                goal_instruction=GOAL_INSTRUCTIONS[request.goal],
                question=request.question,
                context=context,
            )
            for attempt in range(1, self.config.max_retries + 2):
                stage("drafting", attempt=attempt)
                started_at = time.time()
                started = time.monotonic()
                usage = ProviderUsage(None, None, None)
                try:
                    answer, usage = self.provider.generate(model=self.model, prompt=prompt)
                    if answer.disposition != "answered":
                        # Defense in depth: model-authored rejection content is never retained.
                        answer.paragraphs = []
                        answer.limitations = []
                        answer.insufficient_evidence = False
                    stage("validating", attempt=attempt)
                    validate_answer(
                        answer, evidence, self.config, ticker=request.ticker, accession=accession
                    )
                    self.repository.usage(
                        research_id,
                        operation="answer_generation",
                        model=self.model,
                        attempt=attempt,
                        started_at=started_at,
                        finished_at=time.time(),
                        latency_ms=int((time.monotonic() - started) * 1000),
                        usage=usage,
                        outcome="succeeded",
                    )
                    stage("persisting")
                    return self.repository.succeed(research_id, answer)
                except Exception as exc:
                    self.repository.usage(
                        research_id,
                        operation="answer_generation",
                        model=self.model,
                        attempt=attempt,
                        started_at=started_at,
                        finished_at=time.time(),
                        latency_ms=int((time.monotonic() - started) * 1000),
                        usage=usage,
                        outcome=safe_error(exc),
                    )
                    if attempt > self.config.max_retries:
                        raise
        except Exception as exc:
            self.repository.fail(research_id, safe_error(exc))
            raise ResearchFailure(research_id) from None
        raise AssertionError("unreachable")
