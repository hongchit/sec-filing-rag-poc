from __future__ import annotations

import hashlib
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any, Literal, Protocol

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..domain.filings import REQUIRED_ITEMS, safe_error, sha256_bytes
from ..repositories.database import Database

TICKERS = ("AAPL", "MSFT", "NVDA")
Goal = Literal[
    "business", "key_risks", "management_analysis", "market_risk", "legal_and_regulatory_risk"
]
QueryType = Literal["exact_keyword", "semantic_paraphrase"]
Decision = Literal["pending", "accepted", "rejected"]
ITEM_TITLES = {
    "1": "Business",
    "1A": "Risk Factors",
    "3": "Legal Proceedings",
    "7": "Management's Discussion and Analysis",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
}


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    )


class GenerationConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: str
    model: str = "gpt-5.4-mini"
    prompt_version: str
    sampling_seed: int
    workers: int = Field(default=6, ge=1, le=6)
    chunks_per_stratum: int = Field(default=2, ge=1)
    questions_per_chunk: int = Field(default=3, ge=1)
    max_candidates_per_stratum: int = Field(default=5, ge=1)

    @model_validator(mode="after")
    def enough_candidates(self) -> GenerationConfiguration:
        if self.max_candidates_per_stratum < self.chunks_per_stratum:
            raise ValueError("maximum candidates must cover requested chunks")
        if self.questions_per_chunk != 3:
            raise ValueError("this prompt contract requires exactly three questions")
        return self

    def sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))


class GeneratedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=5, max_length=500)
    goal: Goal
    query_type: QueryType

    @field_validator("question")
    @classmethod
    def natural_question(cls, value: str) -> str:
        value = " ".join(value.split())
        lowered = value.lower()
        if any(term in lowered for term in ("the chunk", "the filing text", "hidden metadata")):
            raise ValueError("question refers to prohibited context")
        if not value.endswith("?"):
            raise ValueError("question must end with a question mark")
        return value


class LLMChunkAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meaningful: bool
    explanation: str = Field(min_length=1, max_length=1000)
    questions: list[GeneratedQuestion]

    @model_validator(mode="after")
    def question_contract(self) -> LLMChunkAssessment:
        if not self.meaningful and self.questions:
            raise ValueError("rejected chunks cannot have questions")
        if self.meaningful:
            kinds = [question.query_type for question in self.questions]
            if (
                len(kinds) != 3
                or kinds.count("exact_keyword") != 1
                or kinds.count("semantic_paraphrase") != 2
            ):
                raise ValueError("meaningful chunks require one exact and two semantic questions")
            if len({question.question.casefold() for question in self.questions}) != 3:
                raise ValueError("generated questions must be unique")
        return self


class ReviewQuestion(GeneratedQuestion):
    id: str = Field(pattern=r"^gtq-[0-9a-f]{16}$")
    review_status: Decision = "pending"


class ReviewChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunk_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    text: str
    ticker: Literal["AAPL", "MSFT", "NVDA"]
    company: str
    corpus_version_id: uuid.UUID
    accession: str
    report_date: str
    item: Literal["1", "1A", "3", "7", "7A", "8"]
    item_title: str
    citation: str
    source_start: int
    source_end: int
    source_url: str
    source_metadata: dict[str, Any]
    meaningful: Literal[True] = True
    meaningfulness_explanation: str
    review_status: Decision = "pending"
    questions: list[ReviewQuestion]


class CorpusSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: Literal["AAPL", "MSFT", "NVDA"]
    company: str
    corpus_version_id: uuid.UUID
    accession: str
    report_date: date
    source_url: str
    parser_version: str
    chunking_version: str
    embedding_model: str
    embedding_dimensions: int


class GenerationStratumSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: Literal["AAPL", "MSFT", "NVDA"]
    item: Literal["1", "1A", "3", "7", "7A", "8"]
    available_chunks: int = Field(ge=0)
    screened_chunks: int = Field(ge=0)
    selected_meaningful_chunks: int = Field(ge=0)
    target: int = Field(ge=1)
    source_shortfall: bool
    meaningfulness_shortfall: bool


class ReviewBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["ground-truth-review-v2"] = "ground-truth-review-v2"
    generation_run_id: uuid.UUID
    model: str
    prompt_version: str
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration: GenerationConfiguration
    configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sampling_seed: int
    corpus_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpora: list[CorpusSnapshot]
    generation_summary: list[GenerationStratumSummary]
    chunks: list[ReviewChunk]

    def shortfall_warnings(self) -> list[dict[str, Any]]:
        return [
            {
                "code": "generation_stratum_shortfall",
                "ticker": summary.ticker,
                "item": summary.item,
                "available_chunks": summary.available_chunks,
                "screened_chunks": summary.screened_chunks,
                "selected_meaningful_chunks": summary.selected_meaningful_chunks,
                "target": summary.target,
                "source_shortfall": summary.source_shortfall,
                "meaningfulness_shortfall": summary.meaningfulness_shortfall,
            }
            for summary in self.generation_summary
            if summary.source_shortfall or summary.meaningfulness_shortfall
        ]


class GroundTruthRepository:
    def __init__(self, database: Database, pricing_snapshot: dict[str, Any] | None = None) -> None:
        self.database = database
        self.pricing_snapshot = pricing_snapshot

    def snapshot(self) -> tuple[list[CorpusSnapshot], list[dict[str, Any]]]:
        with self.database.transaction() as connection:
            defaults = connection.execute(
                "SELECT c.ticker,cv.parser_version,cv.chunking_version,cv.embedding_model,"
                "cv.embedding_dimensions FROM public.corpus_activation ca "
                "JOIN public.company c ON c.id=ca.company_id "
                "JOIN silver.corpus_version cv ON cv.id=ca.corpus_version_id AND cv.status='ready' "
                "WHERE ca.is_default AND c.ticker=ANY(%s) ORDER BY c.ticker",
                (list(TICKERS),),
            ).fetchall()
            default_by_ticker = {str(row["ticker"]): dict(row) for row in defaults}
            if set(default_by_ticker) != set(TICKERS):
                raise ValueError("active ready corpora are required for AAPL, MSFT, and NVDA")
            contracts = {
                (
                    row["parser_version"],
                    row["chunking_version"],
                    row["embedding_model"],
                    row["embedding_dimensions"],
                )
                for row in default_by_ticker.values()
            }
            if len(contracts) != 1:
                raise ValueError(
                    "active default corpora have incompatible parser, chunking, or embedding metadata"
                )
            contract = next(iter(contracts))
            rows = connection.execute(
                "WITH compatible AS (SELECT c.ticker,c.name AS company,cv.id AS corpus_version_id,"
                "f.accession,f.report_date,f.source_url,cv.parser_version,cv.chunking_version,"
                "cv.embedding_model,cv.embedding_dimensions,cv.created_at,"
                "row_number() OVER (PARTITION BY c.ticker,f.accession ORDER BY cv.created_at DESC,cv.id DESC) AS rn "
                "FROM silver.corpus_version cv JOIN silver.filing f ON f.id=cv.filing_id "
                "JOIN public.company c ON c.id=f.company_id WHERE cv.status='ready' AND c.ticker=ANY(%s) "
                "AND cv.parser_version=%s AND cv.chunking_version=%s AND cv.embedding_model=%s "
                "AND cv.embedding_dimensions=%s) "
                "SELECT x.ticker,x.company,x.corpus_version_id,x.accession,x.report_date,x.source_url,"
                "x.parser_version,x.chunking_version,x.embedding_model,x.embedding_dimensions,gd.chunk_id,"
                "gd.item,gd.text_content,gd.citation_handle,gd.provenance,ch.source_start,ch.source_end,ch.sha256 "
                "FROM compatible x LEFT JOIN gold.search_document gd ON gd.corpus_version_id=x.corpus_version_id "
                "AND gd.item=ANY(%s) LEFT JOIN silver.chunk ch ON ch.id=gd.chunk_id WHERE x.rn=1 "
                "ORDER BY x.ticker,x.report_date,x.accession,x.corpus_version_id,gd.item,gd.chunk_id",
                (list(TICKERS), *contract, list(REQUIRED_ITEMS)),
            ).fetchall()
        corpora: dict[uuid.UUID, CorpusSnapshot] = {}
        chunks: list[dict[str, Any]] = []
        for raw in rows:
            row = dict(raw)
            corpora.setdefault(
                row["corpus_version_id"],
                CorpusSnapshot.model_validate(
                    {key: row[key] for key in CorpusSnapshot.model_fields}
                ),
            )
            if row["chunk_id"] is not None:
                chunks.append(row)
        ordered_corpora = sorted(
            corpora.values(),
            key=lambda corpus: (
                TICKERS.index(corpus.ticker),
                corpus.report_date,
                corpus.accession,
                str(corpus.corpus_version_id),
            ),
        )
        chunks.sort(
            key=lambda row: (
                TICKERS.index(row["ticker"]),
                row["report_date"],
                row["accession"],
                str(row["corpus_version_id"]),
                REQUIRED_ITEMS.index(row["item"]),
                row["chunk_id"],
            )
        )
        return ordered_corpora, chunks

    def start_run(
        self, run_id: uuid.UUID, config: GenerationConfiguration, prompt_sha: str
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO public.ground_truth_generation_run"
                "(id,model,prompt_version,sampling_seed,configuration,configuration_sha256,prompt_sha256,pricing_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    run_id,
                    config.model,
                    config.prompt_version,
                    config.sampling_seed,
                    json.dumps(config.model_dump(mode="json")),
                    config.sha256(),
                    prompt_sha,
                    json.dumps(self.pricing_snapshot)
                    if self.pricing_snapshot is not None
                    else None,
                ),
            )

    def finish_run(
        self,
        run_id: uuid.UUID,
        *,
        snapshot_sha: str | None = None,
        bundle_sha: str | None = None,
        error: str | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE public.ground_truth_generation_run SET status=%s,corpus_snapshot_sha256=%s,review_bundle_sha256=%s,safe_error=%s,finished_at=now() WHERE id=%s",
                ("failed" if error else "succeeded", snapshot_sha, bundle_sha, error, run_id),
            )

    def usage(
        self,
        run_id: uuid.UUID,
        model: str,
        operation: str,
        started: float,
        usage: Any,
        retry: int,
        error: str | None,
    ) -> None:
        input_tokens = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None) or getattr(
            usage, "output_tokens", None
        )
        total_tokens = getattr(usage, "total_tokens", None)
        status = "failed" if error else ("reported" if total_tokens is not None else "unavailable")
        normalized = error or "succeeded"
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO public.llm_usage(ground_truth_generation_run_id,operation,model,input_tokens,output_tokens,total_tokens,latency_ms,usage_status,normalized_status,retry_count) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    run_id,
                    operation,
                    model,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    int((time.monotonic() - started) * 1000),
                    status,
                    normalized,
                    retry,
                ),
            )

    def verify_chunks(self, chunks: list[ReviewChunk]) -> None:
        with self.database.transaction() as connection:
            for chunk in chunks:
                row = connection.execute(
                    "SELECT ch.sha256,gd.text_content FROM silver.chunk ch JOIN gold.search_document gd ON gd.chunk_id=ch.id JOIN silver.corpus_version cv ON cv.id=ch.corpus_version_id WHERE ch.id=%s AND ch.corpus_version_id=%s AND cv.status='ready'",
                    (chunk.chunk_id, chunk.corpus_version_id),
                ).fetchone()
                if (
                    row is None
                    or str(row["sha256"]) != chunk.chunk_sha256
                    or sha256_bytes(str(row["text_content"]).encode())
                    != sha256_bytes(chunk.text.encode())
                ):
                    raise ValueError(
                        f"source chunk changed or is no longer ready: {chunk.chunk_id}"
                    )


class Assessor(Protocol):
    def assess(self, row: dict[str, Any], run_id: uuid.UUID) -> LLMChunkAssessment: ...


class OpenAIAssessor:
    def __init__(
        self,
        repository: GroundTruthRepository,
        api_key: str,
        config: GenerationConfiguration,
        prompt: str,
        timeout: float,
        max_retries: int = 2,
    ) -> None:
        self.repository, self.config, self.prompt, self.max_retries = (
            repository,
            config,
            prompt,
            max_retries,
        )
        self.client = OpenAI(api_key=api_key, timeout=timeout)

    def close(self) -> None:
        self.client.close()

    def assess(self, row: dict[str, Any], run_id: uuid.UUID) -> LLMChunkAssessment:
        metadata = {
            key: row[key]
            for key in (
                "ticker",
                "company",
                "accession",
                "report_date",
                "item",
                "citation_handle",
                "source_start",
                "source_end",
                "source_url",
                "provenance",
            )
        }
        user = (
            "Metadata:\n"
            + json.dumps(metadata, default=str, sort_keys=True)
            + "\n\n<untrusted_filing_passage>\n"
            + str(row["text_content"])
            + "\n</untrusted_filing_passage>"
        )
        last: Exception | None = None
        for retry in range(self.max_retries + 1):
            started, usage, failure = time.monotonic(), None, None
            try:
                response = self.client.beta.chat.completions.parse(
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": self.prompt},
                        {"role": "user", "content": user},
                    ],
                    response_format=LLMChunkAssessment,
                )
                usage = getattr(response, "usage", None)
                parsed = response.choices[0].message.parsed
                if parsed is None:
                    raise ValueError("structured output was refused or empty")
                return LLMChunkAssessment.model_validate(parsed)
            except Exception as exc:
                last, failure = exc, safe_error(exc)
            finally:
                self.repository.usage(
                    run_id,
                    self.config.model,
                    "ground_truth_screen_and_generate",
                    started,
                    usage,
                    retry,
                    failure,
                )
            if retry < self.max_retries:
                time.sleep(min(2**retry, 2))
        raise RuntimeError(safe_error(last or "structured output failed"))


def deterministic_rank(rows: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    """Rank reproducibly without process-dependent random state."""

    def key(row: dict[str, Any]) -> tuple[str, str]:
        digest = hashlib.sha256(
            f"{seed}:{row['ticker']}:{row['item']}:{row['chunk_id']}".encode()
        ).hexdigest()
        return digest, str(row["chunk_id"])

    return sorted(rows, key=key)


def stable_question_id(chunk_id: str, question: GeneratedQuestion) -> str:
    """Bind an ID to the source chunk and review-relevant question fields."""
    raw = f"{chunk_id}\0{question.query_type}\0{question.goal}\0{question.question}".encode()
    return "gtq-" + hashlib.sha256(raw).hexdigest()[:16]


def _review_chunk(row: dict[str, Any], result: LLMChunkAssessment) -> ReviewChunk:
    questions = [
        ReviewQuestion(
            id=stable_question_id(str(row["chunk_id"]), question), **question.model_dump()
        )
        for question in result.questions
    ]
    return ReviewChunk(
        chunk_id=str(row["chunk_id"]),
        chunk_sha256=str(row["sha256"]),
        text=str(row["text_content"]),
        ticker=row["ticker"],
        company=row["company"],
        corpus_version_id=row["corpus_version_id"],
        accession=row["accession"],
        report_date=str(row["report_date"]),
        item=row["item"],
        item_title=ITEM_TITLES[row["item"]],
        citation=row["citation_handle"],
        source_start=row["source_start"],
        source_end=row["source_end"],
        source_url=row["source_url"],
        source_metadata=row["provenance"],
        meaningfulness_explanation=result.explanation,
        questions=questions,
    )


def generate_bundle(
    repository: GroundTruthRepository,
    assessor: Assessor,
    config: GenerationConfiguration,
    prompt_sha: str,
    run_id: uuid.UUID | None = None,
) -> ReviewBundle:
    run_id = run_id or uuid.uuid4()
    repository.start_run(run_id, config, prompt_sha)
    snapshot_sha: str | None = None
    diagnostics: dict[str, list[dict[str, Any]]] = {}
    try:
        corpora, rows = repository.snapshot()
        snapshot_sha = canonical_sha256([corpus.model_dump(mode="json") for corpus in corpora])
    except Exception as exc:
        repository.finish_run(run_id, error=safe_error(exc))
        raise
    strata = [(ticker, item) for ticker in TICKERS for item in REQUIRED_ITEMS]

    def process(
        stratum: tuple[str, str],
    ) -> tuple[tuple[str, str], list[ReviewChunk], list[dict[str, Any]]]:
        # Bound screening independently for every company and Item stratum.
        candidates = deterministic_rank(
            [row for row in rows if (row["ticker"], row["item"]) == stratum], config.sampling_seed
        )[: config.max_candidates_per_stratum]
        selected, decisions = [], []
        for row in candidates:
            result = assessor.assess(row, run_id)
            decisions.append(
                {
                    "chunk_id": row["chunk_id"],
                    "meaningful": result.meaningful,
                    "explanation": result.explanation,
                }
            )
            if result.meaningful:
                selected.append(_review_chunk(row, result))
                if len(selected) == config.chunks_per_stratum:
                    break
        return stratum, selected, decisions

    chunks: list[ReviewChunk] = []
    summaries: dict[tuple[str, str], GenerationStratumSummary] = {}
    try:
        with ThreadPoolExecutor(max_workers=config.workers) as pool:
            futures = {pool.submit(process, stratum): stratum for stratum in strata}
            for future in as_completed(futures):
                stratum, selected, decisions = future.result()
                diagnostics[f"{stratum[0]}:{stratum[1]}"] = decisions
                chunks.extend(selected)
                available = sum(1 for row in rows if (row["ticker"], row["item"]) == stratum)
                summaries[stratum] = GenerationStratumSummary.model_validate(
                    {
                        "ticker": stratum[0],
                        "item": stratum[1],
                        "available_chunks": available,
                        "screened_chunks": len(decisions),
                        "selected_meaningful_chunks": len(selected),
                        "target": config.chunks_per_stratum,
                        "source_shortfall": available < config.chunks_per_stratum,
                        "meaningfulness_shortfall": len(selected) < config.chunks_per_stratum,
                    }
                )
        # Concurrent completion order varies; artifact order remains deterministic.
        chunks.sort(
            key=lambda chunk: (
                TICKERS.index(chunk.ticker),
                REQUIRED_ITEMS.index(chunk.item),
                chunk.chunk_id,
            )
        )
        bundle = ReviewBundle(
            generation_run_id=run_id,
            model=config.model,
            prompt_version=config.prompt_version,
            prompt_sha256=prompt_sha,
            configuration=config,
            configuration_sha256=config.sha256(),
            sampling_seed=config.sampling_seed,
            corpus_snapshot_sha256=snapshot_sha,
            corpora=corpora,
            generation_summary=[summaries[stratum] for stratum in strata],
            chunks=chunks,
        )
        repository.finish_run(
            run_id,
            snapshot_sha=snapshot_sha,
            bundle_sha=canonical_sha256(bundle.model_dump(mode="json")),
        )
        return bundle
    except Exception as exc:
        repository.finish_run(run_id, snapshot_sha=snapshot_sha, error=safe_error(exc))
        exc.diagnostics = diagnostics  # type: ignore[attr-defined]
        raise


def load_bundle(path: Path) -> ReviewBundle:
    return ReviewBundle.model_validate_json(path.read_text(encoding="utf-8"))


def validate_review(bundle: ReviewBundle, *, require_complete: bool = False) -> None:
    """Validate snapshot integrity and, when requested, the human-review gate."""
    if (
        bundle.configuration_sha256 != bundle.configuration.sha256()
        or bundle.sampling_seed != bundle.configuration.sampling_seed
    ):
        raise ValueError("review bundle configuration metadata was modified")
    if (
        canonical_sha256([corpus.model_dump(mode="json") for corpus in bundle.corpora])
        != bundle.corpus_snapshot_sha256
    ):
        raise ValueError("review bundle corpus snapshot was modified")
    if len({chunk.chunk_id for chunk in bundle.chunks}) != len(bundle.chunks):
        raise ValueError("review bundle has duplicate chunks")
    expected_strata = {(ticker, item) for ticker in TICKERS for item in REQUIRED_ITEMS}
    actual_strata = {(summary.ticker, summary.item) for summary in bundle.generation_summary}
    if actual_strata != expected_strata or len(bundle.generation_summary) != len(expected_strata):
        raise ValueError(
            "review bundle generation summary does not cover each stratum exactly once"
        )
    if require_complete:
        pending = [
            chunk.chunk_id
            for chunk in bundle.chunks
            if chunk.review_status == "pending"
            or any(question.review_status == "pending" for question in chunk.questions)
        ]
        if pending:
            raise ValueError(f"pending human review decisions remain ({len(pending)} chunks)")


def coverage_metadata(records: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    goals = {record["goal"] for record in records}
    companies = {record["ticker"] for record in records}
    items = {record["allowed_items"][0] for record in records}
    query_types = {record["query_type"] for record in records}
    legal = sum(
        record["goal"] == "legal_and_regulatory_risk" or record["allowed_items"] == ["3"]
        for record in records
    )
    nonlegal = sum(
        record["goal"] == "key_risks" and record["allowed_items"] != ["3"] for record in records
    )
    coverage = {
        "accepted_questions": len(records),
        "companies": len(companies),
        "items": len(items),
        "goals": len(goals),
        "query_types": len(query_types),
        "legal_questions": legal,
        "nonlegal_risk_questions": nonlegal,
    }
    checks: list[tuple[str, bool, dict[str, Any]]] = [
        ("question_count", len(records) >= 30, {"actual": len(records), "target": 30}),
        (
            "company_coverage",
            companies == set(TICKERS),
            {"missing": sorted(set(TICKERS) - companies)},
        ),
        (
            "item_coverage",
            items == set(REQUIRED_ITEMS),
            {"missing": sorted(set(REQUIRED_ITEMS) - items)},
        ),
        ("goal_coverage", len(goals) == 5, {"actual": len(goals), "target": 5}),
        (
            "query_type_coverage",
            query_types == {"exact_keyword", "semantic_paraphrase"},
            {"actual": len(query_types), "target": 2},
        ),
        ("legal_coverage", legal > 0, {"actual": legal, "target": 1}),
        ("nonlegal_risk_coverage", nonlegal > 0, {"actual": nonlegal, "target": 1}),
    ]
    warnings = [
        {"code": code, "message": f"coverage target not met: {code}", **details}
        for code, passed, details in checks
        if not passed
    ]
    return coverage, warnings


def finalize_bundle(
    bundle: ReviewBundle,
    repository: GroundTruthRepository,
    dataset_path: Path,
    manifest_path: Path,
    prompt_path: Path,
    config_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Finalize reviewed questions after checking their live ready-corpus lineage."""
    validate_review(bundle, require_complete=True)
    accepted_chunks = [chunk for chunk in bundle.chunks if chunk.review_status == "accepted"]
    repository.verify_chunks(accepted_chunks)
    records = [
        {
            "id": question.id,
            "review_status": "reviewed",
            "question": question.question,
            "ticker": chunk.ticker,
            "goal": question.goal,
            "query_type": question.query_type,
            "allowed_items": [chunk.item],
            "accession": chunk.accession,
            "corpus_version_id": str(chunk.corpus_version_id),
            "relevant_chunk_ids": [chunk.chunk_id],
        }
        for chunk in accepted_chunks
        for question in chunk.questions
        if question.review_status == "accepted"
    ]
    if not records:
        raise ValueError("finalized retrieval evaluation requires at least one accepted question")
    coverage, warnings = coverage_metadata(records)
    corpus_contracts = {
        (
            corpus.parser_version,
            corpus.chunking_version,
            corpus.embedding_model,
            corpus.embedding_dimensions,
        )
        for corpus in bundle.corpora
    }
    if len(corpus_contracts) != 1:
        raise ValueError(
            "snapshotted corpora have incompatible parser, chunking, or embedding metadata"
        )
    prompt_hash = sha256_bytes(prompt_path.read_bytes())
    config_hash = sha256_bytes(config_path.read_bytes())
    serialized = "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records
    )
    corpus0 = bundle.corpora[0]
    manifest = {
        "version": "retrieval-ground-truth-v2",
        "review_status": "reviewed",
        "parser_version": corpus0.parser_version,
        "chunking_version": corpus0.chunking_version,
        "embedding_model": corpus0.embedding_model,
        "embedding_dimensions": corpus0.embedding_dimensions,
        "dataset_sha256": sha256_bytes(serialized.encode()),
        "review_bundle_sha256": canonical_sha256(bundle.model_dump(mode="json")),
        "prompt_sha256": prompt_hash,
        "generation_config_sha256": config_hash,
        "corpus_snapshot_sha256": bundle.corpus_snapshot_sha256,
        "generation_run_id": str(bundle.generation_run_id),
        "coverage": coverage,
        "warnings": warnings,
        "corpora": [
            {
                "ticker": corpus.ticker,
                "accession": corpus.accession,
                "corpus_version_id": str(corpus.corpus_version_id),
            }
            for corpus in bundle.corpora
        ],
    }
    dataset_path.write_text(serialized, encoding="utf-8")
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return records, manifest
