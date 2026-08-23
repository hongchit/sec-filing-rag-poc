from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..core.config import TICKER_RE
from ..domain.filings import SUPPORTED_ITEMS, safe_error, sha256_bytes
from ..repositories.database import Database

RetrievalStrategy = Literal["keyword", "vector", "weighted_hybrid", "rrf"]
BM25_INDEX = "gold.search_document_lexical_bm25"


class SelectedRetrievalConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy: RetrievalStrategy
    candidate_count: int = Field(ge=1, le=1000)
    top_k: int = Field(ge=1, le=100)
    alpha: float | None = Field(default=None, ge=0, le=1)
    rrf_k: int | None = Field(default=None, ge=1, le=1000)
    reason: str | None = None


class RetrievalConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1, max_length=100)
    embedding_model: str = Field(min_length=1)
    embedding_dimensions: int = Field(gt=0)
    candidate_counts: list[int] = Field(min_length=1)
    top_k_values: list[int] = Field(min_length=1)
    hybrid_alphas: list[float] = Field(min_length=1)
    rrf_k_values: list[int] = Field(min_length=1)
    default: SelectedRetrievalConfiguration | None

    @field_validator("candidate_counts", "top_k_values")
    @classmethod
    def positive_unique_counts(cls, values: list[int]) -> list[int]:
        if any(value < 1 or value > 1000 for value in values) or len(values) != len(set(values)):
            raise ValueError("counts must be unique integers between 1 and 1000")
        return values

    @field_validator("hybrid_alphas")
    @classmethod
    def valid_alphas(cls, values: list[float]) -> list[float]:
        if any(value < 0 or value > 1 for value in values) or len(values) != len(set(values)):
            raise ValueError("hybrid alphas must be unique values in [0,1]")
        return values

    @field_validator("rrf_k_values")
    @classmethod
    def valid_rrf_k(cls, values: list[int]) -> list[int]:
        if any(value < 1 for value in values) or len(values) != len(set(values)):
            raise ValueError("RRF k values must be unique positive integers")
        return values

    @model_validator(mode="after")
    def default_is_in_grid(self) -> RetrievalConfiguration:
        if self.default is None:
            return self
        default = self.default
        if default.candidate_count not in self.candidate_counts or default.top_k not in self.top_k_values:
            raise ValueError("default counts must occur in the evaluation grid")
        if default.strategy == "weighted_hybrid" and default.alpha not in self.hybrid_alphas:
            raise ValueError("default hybrid alpha must occur in the evaluation grid")
        if default.strategy == "rrf" and default.rrf_k not in self.rrf_k_values:
            raise ValueError("default RRF k must occur in the evaluation grid")
        return self

    def sha256(self) -> str:
        return sha256_bytes(self.model_dump_json(exclude_none=False).encode())


def load_retrieval_configuration(path: Path) -> RetrievalConfiguration:
    return RetrievalConfiguration.model_validate_json(path.read_text(encoding="utf-8"))


class RetrievalQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    question: str = Field(min_length=1, max_length=2000)
    ticker: str
    corpus_version_id: uuid.UUID
    allowed_items: frozenset[str] | None = None
    strategy: RetrievalStrategy
    candidate_count: int = Field(default=20, ge=1, le=1000)
    top_k: int = Field(default=5, ge=1, le=100)
    alpha: float = Field(default=0.5, ge=0, le=1)
    rrf_k: int = Field(default=60, ge=1, le=1000)

    @field_validator("question")
    @classmethod
    def nonblank_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()

    @field_validator("ticker")
    @classmethod
    def normalized_ticker(cls, value: str) -> str:
        ticker = value.strip().upper()
        if not TICKER_RE.fullmatch(ticker):
            raise ValueError("invalid ticker")
        return ticker

    @field_validator("allowed_items")
    @classmethod
    def supported_items(cls, value: frozenset[str] | None) -> frozenset[str] | None:
        if value is not None and (not value or not value <= SUPPORTED_ITEMS):
            raise ValueError("allowed items must be a non-empty subset of supported filing items")
        return value

    @model_validator(mode="after")
    def top_k_not_above_candidates(self) -> RetrievalQuery:
        if self.top_k > self.candidate_count:
            raise ValueError("top_k cannot exceed candidate_count")
        return self


@dataclass(frozen=True)
class RetrievalResult:
    chunk_id: str
    ticker: str
    accession: str
    item: str
    rank: int
    strategy: RetrievalStrategy
    score: float
    text: str
    citation_handle: str
    provenance: dict[str, Any]


@dataclass(frozen=True)
class Candidate:
    result: RetrievalResult
    score: float
    rank: int


@dataclass(frozen=True)
class CorpusIdentity:
    company_id: uuid.UUID
    filing_id: uuid.UUID
    ticker: str
    accession: str
    embedding_model: str
    embedding_dimensions: int


def normalize_scores(candidates: list[Candidate]) -> dict[str, float]:
    """Min-max normalize scores; an equal-score set receives uniform weight."""
    if not candidates:
        return {}
    scores = [candidate.score for candidate in candidates]
    low, high = min(scores), max(scores)
    if high == low:
        return {candidate.result.chunk_id: 1.0 for candidate in candidates}
    return {candidate.result.chunk_id: (candidate.score - low) / (high - low) for candidate in candidates}


def _fuse(
    keyword: list[Candidate], vector: list[Candidate], strategy: RetrievalStrategy, alpha: float, rrf_k: int
) -> list[RetrievalResult]:
    by_id = {candidate.result.chunk_id: candidate.result for candidate in keyword + vector}
    keyword_rank = {candidate.result.chunk_id: candidate.rank for candidate in keyword}
    vector_rank = {candidate.result.chunk_id: candidate.rank for candidate in vector}
    keyword_score, vector_score = normalize_scores(keyword), normalize_scores(vector)
    scored: list[tuple[float, int, str]] = []
    for chunk_id in by_id:
        if strategy == "weighted_hybrid":
            score = alpha * vector_score.get(chunk_id, 0.0) + (1 - alpha) * keyword_score.get(chunk_id, 0.0)
        else:
            score = sum(
                1 / (rrf_k + rank + 1)
                for rank in (keyword_rank.get(chunk_id), vector_rank.get(chunk_id))
                if rank is not None
            )
        best_rank = min(keyword_rank.get(chunk_id, 10**9), vector_rank.get(chunk_id, 10**9))
        scored.append((score, best_rank, chunk_id))
    # Fusion ties use best source rank, then stable chunk ID.
    scored.sort(key=lambda value: (-value[0], value[1], value[2]))
    return [
        replace(by_id[chunk_id], rank=index, strategy=strategy, score=score)
        for index, (score, _, chunk_id) in enumerate(scored, 1)
    ]


def weighted_hybrid(keyword: list[Candidate], vector: list[Candidate], alpha: float) -> list[RetrievalResult]:
    return _fuse(keyword, vector, "weighted_hybrid", alpha, 60)


def reciprocal_rank_fusion(
    keyword: list[Candidate], vector: list[Candidate], k: int
) -> list[RetrievalResult]:
    return _fuse(keyword, vector, "rrf", 0.5, k)


class QueryEmbedder(Protocol):
    def embed(self, text: str, evaluation_run_id: uuid.UUID | None = None) -> list[float]: ...


class OpenAIQueryEmbedder:
    def __init__(self, database: Database, api_key: str, model: str, dimensions: int, timeout: float) -> None:
        self.database, self.model, self.dimensions = database, model, dimensions
        self.client = OpenAI(api_key=api_key, timeout=timeout)

    def close(self) -> None:
        self.client.close()

    def embed(self, text: str, evaluation_run_id: uuid.UUID | None = None) -> list[float]:
        started = time.monotonic()
        status, normalized, input_tokens, total_tokens = "failed", "failed", None, None
        try:
            response = self.client.embeddings.create(
                model=self.model, dimensions=self.dimensions, input=[text]
            )
            vector = response.data[0].embedding
            if len(response.data) != 1 or len(vector) != self.dimensions:
                raise ValueError("query embedding response dimension or count mismatch")
            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "prompt_tokens", None)
            total_tokens = getattr(usage, "total_tokens", None)
            status = "reported" if total_tokens is not None else "unavailable"
            normalized = "succeeded"
            return vector
        except Exception as exc:
            normalized = safe_error(exc)
            raise RuntimeError(normalized) from None
        finally:
            with self.database.transaction() as connection:
                connection.execute(
                    "INSERT INTO public.llm_usage(evaluation_run_id,operation,model,input_tokens,"
                    "output_tokens,total_tokens,latency_ms,usage_status,normalized_status) "
                    "VALUES (%s,'query_embedding',%s,%s,NULL,%s,%s,%s,%s)",
                    (
                        evaluation_run_id,
                        self.model,
                        input_tokens,
                        total_tokens,
                        int((time.monotonic() - started) * 1000),
                        status,
                        normalized,
                    ),
                )


class RetrievalRepository:
    _SELECT = (
        "SELECT gd.chunk_id,c.ticker,f.accession,gd.item,gd.text_content,gd.citation_handle,gd.provenance,"
    )
    # BM25 and vector search share the exact corpus, company, accession, and Item filters.
    _FILTERS = (
        " FROM gold.search_document gd JOIN public.company c ON c.id=gd.company_id "
        "JOIN silver.filing f ON f.id=gd.filing_id WHERE gd.company_id=%s AND gd.corpus_version_id=%s "
        "AND gd.filing_id=%s AND f.accession=%s AND (%s::text[] IS NULL OR gd.item=ANY(%s::text[])) "
    )

    def __init__(self, database: Database) -> None:
        self.database = database

    def identity(self, query: RetrievalQuery, config: RetrievalConfiguration) -> CorpusIdentity:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT c.id AS company_id,f.id AS filing_id,c.ticker,f.accession,cv.embedding_model,"
                "cv.embedding_dimensions FROM silver.corpus_version cv JOIN silver.filing f ON f.id=cv.filing_id "
                "JOIN public.company c ON c.id=f.company_id WHERE cv.id=%s AND cv.status='ready' AND c.ticker=%s "
                "AND c.enabled",
                (query.corpus_version_id, query.ticker),
            ).fetchone()
        if row is None:
            raise ValueError("unknown company, non-ready corpus, or corpus/company mismatch")
        if (row["embedding_model"], row["embedding_dimensions"]) != (
            config.embedding_model,
            config.embedding_dimensions,
        ):
            raise ValueError("retrieval configuration and corpus embedding metadata are incompatible")
        return CorpusIdentity(**dict(row))

    @staticmethod
    def _params(identity: CorpusIdentity, query: RetrievalQuery) -> tuple[Any, ...]:
        items = sorted(query.allowed_items) if query.allowed_items else None
        return (
            identity.company_id,
            query.corpus_version_id,
            identity.filing_id,
            identity.accession,
            items,
            items,
        )

    def keyword(self, query: RetrievalQuery, identity: CorpusIdentity) -> list[Candidate]:
        statement = self._SELECT + (
            "-(gd.lexical_document <@> to_bm25query(%s,'"
            + BM25_INDEX
            + "')) AS score"
            + self._FILTERS
            + "ORDER BY gd.lexical_document <@> to_bm25query(%s,'"
            + BM25_INDEX
            + "'),gd.chunk_id LIMIT %s"
        )
        params = (query.question,) + self._params(identity, query) + (query.question, query.candidate_count)
        return self._candidates(statement, params, "keyword")

    def vector(
        self, query: RetrievalQuery, identity: CorpusIdentity, embedding: list[float]
    ) -> list[Candidate]:
        statement = self._SELECT + (
            "1-(gd.embedding <=> %s::vector) AS score"
            + self._FILTERS
            + "ORDER BY gd.embedding <=> %s::vector,gd.chunk_id LIMIT %s"
        )
        params = (embedding,) + self._params(identity, query) + (embedding, query.candidate_count)
        return self._candidates(statement, params, "vector")

    def _candidates(
        self, statement: str, params: tuple[Any, ...], strategy: RetrievalStrategy
    ) -> list[Candidate]:
        with self.database.transaction() as connection:
            rows = connection.execute(statement, params).fetchall()
        output: list[Candidate] = []
        for rank, row in enumerate(rows, 1):
            score = float(row["score"])
            result = RetrievalResult(
                str(row["chunk_id"]),
                row["ticker"],
                row["accession"],
                row["item"],
                rank,
                strategy,
                score,
                row["text_content"],
                row["citation_handle"],
                cast(dict[str, Any], row["provenance"]),
            )
            output.append(Candidate(result, score, rank))
        return output


class RetrievalService:
    def __init__(
        self, repository: RetrievalRepository, embedder: QueryEmbedder, config: RetrievalConfiguration
    ) -> None:
        self.repository, self.embedder, self.config = repository, embedder, config

    def retrieve(
        self,
        query: RetrievalQuery,
        *,
        embedding: list[float] | None = None,
        evaluation_run_id: uuid.UUID | None = None,
    ) -> list[RetrievalResult]:
        identity = self.repository.identity(query, self.config)
        keyword: list[Candidate] = []
        vector: list[Candidate] = []
        if query.strategy in {"keyword", "weighted_hybrid", "rrf"}:
            keyword = self.repository.keyword(query, identity)
        if query.strategy in {"vector", "weighted_hybrid", "rrf"}:
            vector_embedding = (
                embedding if embedding is not None else self.embedder.embed(query.question, evaluation_run_id)
            )
            vector = self.repository.vector(query, identity, vector_embedding)
        if query.strategy == "keyword":
            results = [candidate.result for candidate in keyword]
        elif query.strategy == "vector":
            results = [candidate.result for candidate in vector]
        elif query.strategy == "weighted_hybrid":
            results = weighted_hybrid(keyword, vector, query.alpha)
        else:
            results = reciprocal_rank_fusion(keyword, vector, query.rrf_k)
        return results[: query.top_k]


def result_as_dict(result: RetrievalResult) -> dict[str, Any]:
    return {
        "chunk_id": result.chunk_id,
        "ticker": result.ticker,
        "accession": result.accession,
        "item": result.item,
        "rank": result.rank,
        "strategy": result.strategy,
        "score": result.score,
        "text": result.text,
        "citation_handle": result.citation_handle,
        "provenance": result.provenance,
    }
