from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..generation.service import AnswerParagraph, ResearchGoal


class ResearchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str
    corpus_version_id: uuid.UUID
    goal: ResearchGoal
    question: str
    allowed_items: frozenset[str] | None = None


class ResearchUsage(BaseModel):
    query_embedding_input: int | None = None
    answer_generation_input: int | None = None
    answer_generation_output: int | None = None
    complete_request_total: int | None = None
    provider_calls: int


class ResearchEvidence(BaseModel):
    rank: int
    chunk_id: str
    citation_handle: str
    ticker: str
    accession: str
    item: str
    excerpt: str
    source_start: int
    source_end: int
    source_anchor: str | None = None
    source_url: str
    strategy: str
    score: float


class RunDetails(BaseModel):
    accession: str | None = None
    corpus_version_id: uuid.UUID
    retrieval_configuration_sha256: str | None = None
    generation_configuration_sha256: str | None = None
    prompt_sha256: str | None = None
    prompt_id: str
    chat_model: str
    strategy: str | None = None
    alpha: float | None = None
    evidence_count: int
    attempts: int
    latency_ms: int | None = None
    operations: list[dict[str, Any]] = Field(default_factory=list)


class ResearchResponse(BaseModel):
    research_id: uuid.UUID
    ticker: str
    corpus_version_id: uuid.UUID
    goal: ResearchGoal
    question: str
    allowed_items: list[str] | None = None
    status: str
    prompt_id: str
    chat_model: str
    safe_error: str | None = None
    answer: list[AnswerParagraph] | None = None
    limitations: list[str] | None = None
    insufficient_evidence: bool | None = None
    policy_refusal: bool | None = None
    evidence: list[ResearchEvidence]
    usage: ResearchUsage
    run_details: RunDetails
    created_at: datetime
    finished_at: datetime | None = None


class ResearchHistory(BaseModel):
    items: list[ResearchResponse]
    next_cursor: str | None = None


class FeedbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_type: Literal["research_answer"]
    result_id: uuid.UUID
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=1000)

    @field_validator("comment")
    @classmethod
    def trim_comment(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value.strip()


class FeedbackResponse(FeedbackCreate):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
