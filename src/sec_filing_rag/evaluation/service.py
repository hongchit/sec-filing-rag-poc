from __future__ import annotations

import json
import statistics
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..domain.filings import SUPPORTED_ITEMS, sha256_bytes
from ..repositories.database import Database
from ..retrieval.service import (
    RetrievalConfiguration,
    RetrievalQuery,
    RetrievalResult,
    RetrievalService,
    RetrievalStrategy,
)


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^gtq-[0-9a-f]{16}$")
    review_status: Literal["reviewed"]
    question: str = Field(min_length=1, max_length=2000)
    ticker: Literal["AAPL", "MSFT", "NVDA"]
    goal: Literal[
        "business", "key_risks", "management_analysis", "market_risk", "legal_and_regulatory_risk"
    ]
    query_type: Literal["exact_keyword", "semantic_paraphrase"]
    allowed_items: frozenset[str]
    accession: str
    corpus_version_id: uuid.UUID
    relevant_chunk_ids: frozenset[str] = Field(min_length=1)

    @field_validator("allowed_items")
    @classmethod
    def supported_items(cls, value: frozenset[str]) -> frozenset[str]:
        if not value or not value <= SUPPORTED_ITEMS:
            raise ValueError("allowed items must be a non-empty supported subset")
        return value

    @field_validator("relevant_chunk_ids")
    @classmethod
    def chunk_ids(cls, value: frozenset[str]) -> frozenset[str]:
        if any(len(chunk_id) != 64 for chunk_id in value):
            raise ValueError("relevant chunk IDs must be SHA-256 identifiers")
        return value


class CorpusManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: Literal["AAPL", "MSFT", "NVDA"]
    accession: str
    corpus_version_id: uuid.UUID


class CorpusManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["retrieval-ground-truth-v2"]
    review_status: Literal["reviewed"]
    parser_version: str
    chunking_version: str
    embedding_model: str
    embedding_dimensions: int = Field(gt=0)
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_run_id: uuid.UUID
    corpora: list[CorpusManifestEntry]
    coverage: dict[str, Any]
    warnings: list[dict[str, Any]]


def dataset_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_cases(path: Path) -> list[EvaluationCase]:
    cases = [
        EvaluationCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not cases:
        raise ValueError("retrieval evaluation requires at least one case")
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("evaluation case IDs must be unique")
    return cases


def load_manifest(path: Path) -> CorpusManifest:
    return CorpusManifest.model_validate_json(path.read_text(encoding="utf-8"))


def hit_rate(results: list[RetrievalResult], relevant: frozenset[str]) -> float:
    return float(any(result.chunk_id in relevant for result in results))


def reciprocal_rank(results: list[RetrievalResult], relevant: frozenset[str]) -> float:
    for rank, result in enumerate(results, 1):
        if result.chunk_id in relevant:
            return 1.0 / rank
    return 0.0


def validate_review_gate(
    cases: list[EvaluationCase],
    manifest: CorpusManifest,
    dataset_path: Path,
    config: RetrievalConfiguration,
) -> None:
    """Reject unreviewed, modified, or corpus-incompatible benchmark artifacts."""
    if manifest.review_status != "reviewed" or any(
        case.review_status != "reviewed" for case in cases
    ):
        raise ValueError("dataset and every case must be human-reviewed before benchmarking")
    if manifest.dataset_sha256 != dataset_sha256(dataset_path):
        raise ValueError("manifest dataset checksum does not match")
    if (manifest.embedding_model, manifest.embedding_dimensions) != (
        config.embedding_model,
        config.embedding_dimensions,
    ):
        raise ValueError("manifest and retrieval embedding metadata are incompatible")
    manifest_corpora = {
        (entry.ticker, entry.accession, entry.corpus_version_id) for entry in manifest.corpora
    }
    for case in cases:
        if (case.ticker, case.accession, case.corpus_version_id) not in manifest_corpora:
            raise ValueError(f"{case.id} does not match the reviewed corpus manifest")


def validate_database_lineage(database: Database, cases: list[EvaluationCase]) -> None:
    """Ensure reviewed chunks still belong to their declared ready corpora."""
    with database.transaction() as connection:
        for case in cases:
            rows = connection.execute(
                "SELECT gd.chunk_id FROM gold.search_document gd JOIN public.company c ON c.id=gd.company_id "
                "JOIN silver.filing f ON f.id=gd.filing_id JOIN silver.corpus_version cv "
                "ON cv.id=gd.corpus_version_id WHERE gd.chunk_id=ANY(%s) AND c.ticker=%s "
                "AND f.accession=%s AND cv.id=%s AND cv.status='ready'",
                (
                    sorted(case.relevant_chunk_ids),
                    case.ticker,
                    case.accession,
                    case.corpus_version_id,
                ),
            ).fetchall()
            if {str(row["chunk_id"]) for row in rows} != set(case.relevant_chunk_ids):
                raise ValueError(f"{case.id} has missing or wrong-company relevant chunk lineage")


@dataclass(frozen=True)
class EvaluationApproach:
    strategy: RetrievalStrategy
    candidate_count: int
    top_k: int
    alpha: float = 0.5
    rrf_k: int = 60

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "candidate_count": self.candidate_count,
            "top_k": self.top_k,
            "alpha": self.alpha,
            "rrf_k": self.rrf_k,
        }


def approaches(config: RetrievalConfiguration) -> list[EvaluationApproach]:
    output: list[EvaluationApproach] = []
    for candidate_count in config.candidate_counts:
        for top_k in config.top_k_values:
            if top_k > candidate_count:
                continue
            output.append(EvaluationApproach("keyword", candidate_count, top_k))
            output.append(EvaluationApproach("vector", candidate_count, top_k))
            output.extend(
                EvaluationApproach("weighted_hybrid", candidate_count, top_k, alpha=alpha)
                for alpha in config.hybrid_alphas
            )
            output.extend(
                EvaluationApproach("rrf", candidate_count, top_k, rrf_k=k)
                for k in config.rrf_k_values
            )
    return output


_SIMPLICITY = {"keyword": 0, "vector": 1, "weighted_hybrid": 2, "rrf": 3}


def select_winner(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot select a winner without results")
    # Prefer quality, then latency, then simplicity for a stable winner.
    return sorted(
        rows,
        key=lambda row: (
            -float(row["mrr"]),
            -float(row["hit_rate"]),
            float(row["median_latency_ms"]),
            _SIMPLICITY[str(row["configuration"]["strategy"])],
        ),
    )[0]


class RetrievalEvaluator:
    def __init__(
        self, database: Database, service: RetrievalService, config: RetrievalConfiguration
    ) -> None:
        self.database, self.service, self.config = database, service, config

    def run(
        self,
        cases: list[EvaluationCase],
        dataset_hash: str,
        coverage: dict[str, Any] | None = None,
        warnings: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        run_id = uuid.uuid4()
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO public.retrieval_evaluation_run(id,dataset_sha256,configuration_sha256) "
                "VALUES (%s,%s,%s)",
                (run_id, dataset_hash, self.config.sha256()),
            )
        embeddings: dict[str, list[float]] = {}
        rows: list[dict[str, Any]] = []
        try:
            # Embed once per question so grid latency measures retrieval, not provider calls.
            for case in cases:
                embeddings[case.id] = self.service.embedder.embed(case.question, run_id)
            for approach in approaches(self.config):
                hit_values, rr_values, latencies, rankings = [], [], [], []
                for case in cases:
                    query = RetrievalQuery(
                        question=case.question,
                        ticker=case.ticker,
                        corpus_version_id=case.corpus_version_id,
                        allowed_items=case.allowed_items,
                        **approach.as_dict(),
                    )
                    started = time.monotonic()
                    results = self.service.retrieve(query, embedding=embeddings[case.id])
                    latencies.append((time.monotonic() - started) * 1000)
                    hit_values.append(hit_rate(results, case.relevant_chunk_ids))
                    rr_values.append(reciprocal_rank(results, case.relevant_chunk_ids))
                    rankings.append(
                        {
                            "case_id": case.id,
                            "chunk_ids": [result.chunk_id for result in results],
                            "hit": hit_values[-1],
                            "reciprocal_rank": rr_values[-1],
                        }
                    )
                rows.append(
                    {
                        "configuration": approach.as_dict(),
                        "hit_rate": statistics.fmean(hit_values),
                        "mrr": statistics.fmean(rr_values),
                        "median_latency_ms": statistics.median(latencies),
                        "questions": rankings,
                    }
                )
            winner = select_winner(rows)
            artifact = {
                "evaluation_run_id": str(run_id),
                "dataset_sha256": dataset_hash,
                "configuration_sha256": self.config.sha256(),
                "course_commit": "bc7b6aad6b92a5611d3d37bf7521a363f3b9d398",
                "results": rows,
                "selected_default": winner["configuration"],
                "coverage": coverage or {},
                "warnings": warnings or [],
                "failures": [],
            }
            with self.database.transaction() as connection:
                connection.execute(
                    "UPDATE public.retrieval_evaluation_run SET status='succeeded',"
                    "selected_configuration=%s,finished_at=now() WHERE id=%s",
                    (json.dumps(winner["configuration"]), run_id),
                )
            return artifact
        except Exception as exc:
            with self.database.transaction() as connection:
                connection.execute(
                    "UPDATE public.retrieval_evaluation_run SET status='failed',safe_error=%s,"
                    "finished_at=now() WHERE id=%s",
                    (str(exc)[:500], run_id),
                )
            raise
