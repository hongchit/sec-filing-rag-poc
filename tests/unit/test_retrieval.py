from __future__ import annotations

import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from sec_filing_rag.evaluation.service import (
    CorpusManifest,
    EvaluationCase,
    hit_rate,
    load_cases,
    reciprocal_rank,
    select_winner,
    validate_review_gate,
)
from sec_filing_rag.retrieval.service import (
    Candidate,
    RetrievalQuery,
    RetrievalResult,
    load_retrieval_configuration,
    normalize_scores,
    reciprocal_rank_fusion,
    weighted_hybrid,
)


def result(chunk_id: str, rank: int, score: float, strategy: str = "keyword") -> RetrievalResult:
    return RetrievalResult(
        chunk_id,
        "AAPL",
        "accession",
        "1A",
        rank,
        strategy,
        score,
        "text",
        f"citation-{chunk_id}",
        {"source": "SEC"},
    )  # type: ignore[arg-type]


def candidate(chunk_id: str, rank: int, score: float) -> Candidate:
    value = result(chunk_id, rank, score)
    return Candidate(value, score, rank)


def test_query_validation_rejects_blank_unsupported_items_and_bad_counts() -> None:
    valid = {
        "question": "risk",
        "ticker": "aapl",
        "corpus_version_id": uuid.uuid4(),
        "strategy": "keyword",
    }
    assert RetrievalQuery(**valid).ticker == "AAPL"
    with pytest.raises(ValidationError):
        RetrievalQuery(**{**valid, "question": " "})
    with pytest.raises(ValidationError):
        RetrievalQuery(**{**valid, "allowed_items": ["2"]})
    with pytest.raises(ValidationError):
        RetrievalQuery(**{**valid, "candidate_count": 4, "top_k": 5})
    with pytest.raises(ValidationError):
        RetrievalQuery(**{**valid, "strategy": "fallback"})


def test_score_normalization_and_weighted_fusion() -> None:
    keyword = [candidate("a", 1, 4), candidate("b", 2, 2)]
    vector = [candidate("b", 1, 0.9), candidate("c", 2, 0.1)]
    assert normalize_scores(keyword) == {"a": 1.0, "b": 0.0}
    fused = weighted_hybrid(keyword, vector, 0.5)
    assert [(value.chunk_id, value.score) for value in fused] == [("a", 0.5), ("b", 0.5), ("c", 0.0)]


def test_flat_normalization_is_one_and_ties_use_rank_then_chunk_id() -> None:
    assert normalize_scores([candidate("b", 2, 7), candidate("a", 1, 7)]) == {"b": 1, "a": 1}
    fused = weighted_hybrid(
        [candidate("b", 1, 1), candidate("a", 1, 1)],
        [candidate("a", 1, 1), candidate("b", 1, 1)],
        0.5,
    )
    assert [value.chunk_id for value in fused] == ["a", "b"]


def test_rrf_formula_and_deterministic_order() -> None:
    fused = reciprocal_rank_fusion(
        [candidate("a", 1, 1), candidate("b", 2, 0.5)],
        [candidate("b", 1, 1), candidate("a", 2, 0.5)],
        10,
    )
    assert fused[0].chunk_id == "a"
    assert fused[0].score == pytest.approx(1 / 12 + 1 / 13)
    assert [value.rank for value in fused] == [1, 2]


def test_metrics_and_winner_tie_breaks() -> None:
    values = [result("x", 1, 1), result("relevant", 2, 0.5)]
    assert hit_rate(values, frozenset({"relevant"})) == 1
    assert reciprocal_rank(values, frozenset({"relevant"})) == 0.5
    assert reciprocal_rank(values, frozenset({"missing"})) == 0
    rows = [
        {"mrr": 0.5, "hit_rate": 0.8, "median_latency_ms": 2, "configuration": {"strategy": "vector"}},
        {"mrr": 0.5, "hit_rate": 0.8, "median_latency_ms": 1, "configuration": {"strategy": "keyword"}},
    ]
    assert select_winner(rows)["configuration"]["strategy"] == "keyword"


def test_tracked_configuration_grid_and_finalized_schema() -> None:
    config = load_retrieval_configuration(Path("config/retrieval.json"))
    assert config.candidate_counts == [10, 20, 50]
    assert config.top_k_values == [5, 10]
    assert config.default is None
    case = {
        "id": "gtq-0123456789abcdef",
        "review_status": "reviewed",
        "question": "What material risk is disclosed?",
        "ticker": "AAPL",
        "goal": "key_risks",
        "query_type": "exact_keyword",
        "allowed_items": ["1A"],
        "accession": "0000320193-25-000079",
        "corpus_version_id": str(uuid.uuid4()),
        "relevant_chunk_ids": ["a" * 64],
    }
    assert EvaluationCase.model_validate(case).review_status == "reviewed"
    with pytest.raises(ValidationError):
        EvaluationCase.model_validate({**case, "id": "ret-001"})
    manifest = {
        "version": "retrieval-ground-truth-v2",
        "review_status": "reviewed",
        "parser_version": "p",
        "chunking_version": "c",
        "embedding_model": "e",
        "embedding_dimensions": 3,
        "dataset_sha256": "a" * 64,
        "review_bundle_sha256": "b" * 64,
        "prompt_sha256": "c" * 64,
        "generation_config_sha256": "d" * 64,
        "corpus_snapshot_sha256": "e" * 64,
        "generation_run_id": str(uuid.uuid4()),
        "corpora": [],
        "coverage": {"accepted_questions": 1},
        "warnings": [{"code": "question_count"}],
    }
    assert CorpusManifest.model_validate(manifest).review_status == "reviewed"
    with pytest.raises(ValidationError):
        CorpusManifest.model_validate(
            {key: value for key, value in manifest.items() if key != "prompt_sha256"}
        )


def test_partial_dataset_loads_and_manifest_matches_exact_corpus(tmp_path: Path) -> None:
    first_version, second_version = uuid.uuid4(), uuid.uuid4()
    case_data = {
        "id": "gtq-0123456789abcdef",
        "review_status": "reviewed",
        "question": "What material risk is disclosed?",
        "ticker": "AAPL",
        "goal": "key_risks",
        "query_type": "exact_keyword",
        "allowed_items": ["1A"],
        "accession": "new-accession",
        "corpus_version_id": str(second_version),
        "relevant_chunk_ids": ["a" * 64],
    }
    dataset = tmp_path / "partial.jsonl"
    dataset.write_text(__import__("json").dumps(case_data) + "\n", encoding="utf-8")
    cases = load_cases(dataset)
    config = load_retrieval_configuration(Path("config/retrieval.json"))
    manifest = CorpusManifest.model_validate(
        {
            "version": "retrieval-ground-truth-v2",
            "review_status": "reviewed",
            "parser_version": "p",
            "chunking_version": "c",
            "embedding_model": config.embedding_model,
            "embedding_dimensions": config.embedding_dimensions,
            "dataset_sha256": __import__("hashlib").sha256(dataset.read_bytes()).hexdigest(),
            "review_bundle_sha256": "b" * 64,
            "prompt_sha256": "c" * 64,
            "generation_config_sha256": "d" * 64,
            "corpus_snapshot_sha256": "e" * 64,
            "generation_run_id": str(uuid.uuid4()),
            "corpora": [
                {"ticker": "AAPL", "accession": "old-accession", "corpus_version_id": first_version},
                {"ticker": "AAPL", "accession": "new-accession", "corpus_version_id": second_version},
            ],
            "coverage": {"accepted_questions": 1},
            "warnings": [{"code": "question_count"}],
        }
    )
    validate_review_gate(cases, manifest, dataset, config)


class FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class RecordingConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows, self.calls = rows, []

    def execute(self, statement: str, params: tuple[Any, ...]) -> FakeCursor:
        self.calls.append((statement, params))
        return FakeCursor(self.rows)


class RecordingDatabase:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.connection = RecordingConnection(rows)

    @contextmanager
    def transaction(self):  # type: ignore[no-untyped-def]
        yield self.connection


def test_migration_has_pinned_bm25_contract_and_prefilter_indexes() -> None:
    migration = Path("migrations/versions/0001_schema.sql").read_text(encoding="utf-8")
    assert "USING bm25 (lexical_document) WITH (text_config='english')" in migration
    assert "search_document_company_corpus_filing_item" in migration
    assert "evaluation_run_id" in migration
    assert "llm_usage_single_owner" in migration


def test_repository_paths_parameterize_values_and_share_identical_filters() -> None:
    from sec_filing_rag.retrieval.service import CorpusIdentity, RetrievalRepository

    rows = [
        {
            "chunk_id": "a" * 64,
            "ticker": "AAPL",
            "accession": "accession",
            "item": "1A",
            "text_content": "risk",
            "citation_handle": "citation",
            "provenance": {},
            "score": 1.0,
        }
    ]
    database = RecordingDatabase(rows)
    repository = RetrievalRepository(database)  # type: ignore[arg-type]
    query = RetrievalQuery(
        question="supply chain",
        ticker="AAPL",
        corpus_version_id=uuid.uuid4(),
        strategy="keyword",
        allowed_items=frozenset({"1A"}),
        candidate_count=10,
        top_k=5,
    )
    identity = CorpusIdentity(uuid.uuid4(), uuid.uuid4(), "AAPL", "accession", "model", 3)
    repository.keyword(query, identity)
    keyword_sql, keyword_params = database.connection.calls[-1]
    repository.vector(query, identity, [0.1, 0.2, 0.3])
    vector_sql, vector_params = database.connection.calls[-1]
    common = (
        "WHERE gd.company_id=%s AND gd.corpus_version_id=%s AND gd.filing_id=%s AND f.accession=%s "
        "AND (%s::text[] IS NULL OR gd.item=ANY(%s::text[]))"
    )
    assert common in keyword_sql and common in vector_sql
    assert "supply chain" not in keyword_sql
    assert keyword_params[1:7] == vector_params[1:7]
    assert "to_bm25query(%s,'gold.search_document_lexical_bm25')" in keyword_sql
    assert "<=> %s::vector" in vector_sql


def test_query_embedder_persists_reported_unavailable_and_failed_usage() -> None:
    from types import SimpleNamespace

    from sec_filing_rag.retrieval.service import OpenAIQueryEmbedder

    class Embeddings:
        def __init__(self, response: object) -> None:
            self.response = response

        def create(self, **kwargs: object) -> object:
            if isinstance(self.response, BaseException):
                raise self.response
            return self.response

    database = RecordingDatabase([])
    embedder = object.__new__(OpenAIQueryEmbedder)
    embedder.database, embedder.model, embedder.dimensions = database, "model", 3
    embedder.client = SimpleNamespace(
        embeddings=Embeddings(
            SimpleNamespace(
                data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])],
                usage=SimpleNamespace(prompt_tokens=2, total_tokens=2),
            )
        )
    )
    assert embedder.embed("question") == [0.1, 0.2, 0.3]
    assert database.connection.calls[-1][1][-2:] == ("reported", "succeeded")

    embedder.client = SimpleNamespace(
        embeddings=Embeddings(
            SimpleNamespace(
                data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])],
                usage=None,
            )
        )
    )
    embedder.embed("question")
    assert database.connection.calls[-1][1][-2:] == ("unavailable", "succeeded")

    embedder.client = SimpleNamespace(embeddings=Embeddings(TimeoutError("Bearer secret")))
    with pytest.raises(RuntimeError, match="REDACTED"):
        embedder.embed("question")
    assert database.connection.calls[-1][1][-2] == "failed"
    assert "secret" not in database.connection.calls[-1][1][-1]
