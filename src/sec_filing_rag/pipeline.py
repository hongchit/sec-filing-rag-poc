from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import asdict, dataclass

from openai import OpenAI

from .config import Settings, load_companies
from .domain import (
    REQUIRED_ITEMS,
    Chunk,
    compatibility_key,
    extract_sections,
    make_chunks,
    safe_error,
    sanitize_filing_html,
    sha256_bytes,
)
from .sec import SecClient
from .store import Store


@dataclass(frozen=True)
class CompanyResult:
    ticker: str
    run_id: uuid.UUID
    outcome: str
    accession: str | None
    coverage: dict[str, str]
    section_count: int
    chunk_count: int
    search_document_count: int
    embedding_usage_status: str
    corpus_disposition: str
    error: str | None = None


@dataclass(frozen=True)
class BatchResult:
    status: str
    results: list[CompanyResult]


# Kept as a public alias for callers that imported the Milestone 2 result name.
Result = CompanyResult


class IngestionPipeline:
    def __init__(self, settings: Settings, store: Store) -> None:
        self.settings = settings
        self.store = store

    def run_batch(
        self, target: str, trigger: str = "api", kestra_execution_id: str | None = None
    ) -> BatchResult:
        config = load_companies(self.settings.company_config_path)
        self.store.load_configuration(config, self.settings.company_config_path)
        enabled = [entry.ticker for entry in config.companies if entry.enabled]
        tickers = enabled if target == "all" else [target]
        results: list[CompanyResult] = []
        for ticker in tickers:
            try:
                results.append(self.run_company(ticker, trigger, kestra_execution_id=kestra_execution_id))
            except Exception as exc:
                error = safe_error(
                    exc,
                    (
                        self.settings.openai_api_key,
                        self.settings.ingestion_api_token,
                        self.settings.sec_user_agent,
                    ),
                )
                results.append(
                    CompanyResult(
                        ticker,
                        uuid.uuid4(),
                        "failed",
                        None,
                        {},
                        0,
                        0,
                        0,
                        "failed",
                        "previous_preserved",
                        error,
                    )
                )
        failures = sum(result.outcome == "failed" for result in results)
        overall = "failed" if failures == len(results) else "partial_failure" if failures else "succeeded"
        return BatchResult(overall, results)

    def run(self, ticker: str, item: str = "corpus", trigger: str = "api") -> CompanyResult:
        del item
        config = load_companies(self.settings.company_config_path)
        self.store.load_configuration(config, self.settings.company_config_path)
        return self.run_company(ticker, trigger)

    def run_historical(
        self,
        *,
        preparation_request_id: uuid.UUID,
        ticker: str,
        requested_year: int,
        selected_accession: str,
        kestra_execution_id: str | None,
    ) -> BatchResult:
        self.store.validate_preparation_callback(
            preparation_request_id, ticker, requested_year, selected_accession
        )
        result = self.run_company(
            ticker,
            "historical",
            selected_accession=selected_accession,
            preparation_request_id=preparation_request_id,
            kestra_execution_id=kestra_execution_id,
        )
        return BatchResult("failed" if result.outcome == "failed" else "succeeded", [result])

    def run_company(
        self,
        ticker: str,
        trigger: str,
        *,
        selected_accession: str | None = None,
        preparation_request_id: uuid.UUID | None = None,
        kestra_execution_id: str | None = None,
    ) -> CompanyResult:
        provisional_key = compatibility_key(
            parser=self.settings.parser_version,
            chunker=self.settings.chunking_version,
            model=self.settings.openai_embedding_model,
            dimensions=self.settings.openai_embedding_dimensions,
            index=self.settings.index_version,
        )
        run_id, company_id = self.store.start_run(
            ticker,
            "corpus",
            trigger,
            provisional_key,
            preparation_request_id,
            kestra_execution_id,
        )
        accession: str | None = None
        stage = "resolve"
        try:
            self.store.stage(run_id, stage, "running")
            sec = SecClient(
                identity=self.settings.sec_user_agent,
                timeout=self.settings.sec_timeout_seconds,
                retries=self.settings.sec_max_retries,
                interval=self.settings.sec_request_interval_seconds,
            )
            cik, name, ticker_fetch = sec.resolve(ticker)
            self.store.stage(run_id, stage, "succeeded", output_count=1)
            stage = "select-filing"
            self.store.stage(run_id, stage, "running")
            filing, submission_fetch, submission = sec.latest_filing(cik)
            if selected_accession is not None:
                discovered_cik, _, candidates = sec.discover_candidates(ticker)
                if discovered_cik != cik:
                    raise ValueError("selected filing issuer changed during callback revalidation")
                selected = next(
                    (candidate for candidate in candidates if candidate.accession == selected_accession),
                    None,
                )
                if selected is None:
                    raise ValueError("selected accession is no longer an original 10-K candidate")
                filing = selected
            accession = filing.accession
            self.store.stage(run_id, stage, "succeeded", output_count=1)
            stage = "download"
            self.store.stage(run_id, stage, "running")
            document = sec.document(cik, filing)
            if len(document.body) > self.settings.sec_max_document_bytes:
                raise ValueError("SEC filing document exceeds configured size limit")
            checksum = sha256_bytes(document.body)
            key = compatibility_key(
                parser=self.settings.parser_version,
                chunker=self.settings.chunking_version,
                model=self.settings.openai_embedding_model,
                dimensions=self.settings.openai_embedding_dimensions,
                index=self.settings.index_version,
                source_checksum=checksum,
            )
            self.store.update_run_key(run_id, key)
            self.store.stage(run_id, stage, "succeeded", output_count=1)
            existing = self.store.ready_corpus(company_id, accession, key)
            if existing is not None:
                self.store.skip_run(run_id)
                if preparation_request_id is not None:
                    self.store.complete_preparation(preparation_request_id, existing["corpus_version_id"])
                return CompanyResult(
                    ticker,
                    run_id,
                    "skipped",
                    accession,
                    existing["coverage"],
                    existing["section_count"],
                    existing["chunk_count"],
                    existing["search_document_count"],
                    existing["embedding_usage_status"],
                    "unchanged",
                    None,
                )

            stage = "extract"
            self.store.stage(run_id, stage, "running")
            narrative = sanitize_filing_html(document.body, max_chars=self.settings.sec_max_narrative_chars)
            sections = extract_sections(narrative)
            chunks: dict[str, list[Chunk]] = {
                item: make_chunks(
                    section.text or "",
                    accession=filing.accession,
                    item=item,
                    version=f"{self.settings.chunking_version}:{key}",
                    size=self.settings.chunk_size_chars,
                    overlap=self.settings.chunk_overlap_chars,
                    base_offset=section.start or 0,
                )
                if section.status == "present"
                else []
                for item, section in sections.items()
            }
            self.store.stage(run_id, stage, "succeeded", input_count=1, output_count=len(sections))
            unusable = [
                item for item in REQUIRED_ITEMS if sections[item].status in {"failed", "not_assessed"}
            ]
            if unusable:
                raise ValueError("corpus extraction incomplete for required items: " + ", ".join(unusable))

            stage = "embed"
            flat_chunks = [chunk for item in REQUIRED_ITEMS for chunk in chunks[item]]
            if not flat_chunks:
                raise ValueError("corpus has no present sections to embed")
            self.store.stage(run_id, stage, "running", input_count=len(flat_chunks))
            started = time.monotonic()
            response = OpenAI(
                api_key=self.settings.openai_api_key,
                timeout=self.settings.openai_timeout_seconds,
            ).embeddings.create(
                model=self.settings.openai_embedding_model,
                input=[chunk.text for chunk in flat_chunks],
                dimensions=self.settings.openai_embedding_dimensions,
            )
            vectors = [entry.embedding for entry in response.data]
            if len(vectors) != len(flat_chunks) or any(
                len(vector) != self.settings.openai_embedding_dimensions for vector in vectors
            ):
                raise ValueError("embedding response dimension or count mismatch")
            embeddings: dict[str, list[list[float]]] = {}
            cursor = 0
            for item in REQUIRED_ITEMS:
                embeddings[item] = vectors[cursor : cursor + len(chunks[item])]
                cursor += len(chunks[item])
            usage_object = getattr(response, "usage", None)
            prompt_tokens = getattr(usage_object, "prompt_tokens", None)
            total_tokens = getattr(usage_object, "total_tokens", None)
            usage = (
                prompt_tokens,
                None,
                total_tokens,
                "reported" if total_tokens is not None else "unavailable",
                int((time.monotonic() - started) * 1000),
            )
            self.store.stage(run_id, stage, "succeeded", output_count=len(vectors))

            stage = "persist-promote"
            self.store.stage(run_id, stage, "running", input_count=len(flat_chunks))
            self.store.persist(
                run_id=run_id,
                company_id=company_id,
                ticker=ticker,
                cik=cik,
                name=name,
                ticker_fetch=ticker_fetch,
                submission_fetch=submission_fetch,
                submission=submission,
                document=document,
                filing=filing,
                sections=sections,
                chunks=chunks,
                embeddings=embeddings,
                key=key,
                parser=self.settings.parser_version,
                chunker=self.settings.chunking_version,
                model=self.settings.openai_embedding_model,
                dimensions=self.settings.openai_embedding_dimensions,
                index=self.settings.index_version,
                usage=usage,
                user_agent_hash=hashlib.sha256(self.settings.sec_user_agent.encode()).hexdigest(),
                promote_default=preparation_request_id is None,
                preparation_request_id=preparation_request_id,
            )
            coverage: dict[str, str] = {item: sections[item].status for item in REQUIRED_ITEMS}
            return CompanyResult(
                ticker,
                run_id,
                "succeeded",
                accession,
                coverage,
                len(sections),
                len(flat_chunks),
                len(flat_chunks),
                usage[3],
                "activated" if preparation_request_id is None else "historical_ready",
                None,
            )
        except Exception as exc:
            error = safe_error(
                exc,
                (
                    self.settings.openai_api_key,
                    self.settings.ingestion_api_token,
                    self.settings.sec_user_agent,
                ),
            )
            self.store.fail_run(run_id, stage, error)
            if preparation_request_id is not None:
                self.store.fail_preparation(preparation_request_id, error)
            return CompanyResult(
                ticker,
                run_id,
                "failed",
                accession,
                {},
                0,
                0,
                0,
                "failed",
                "previous_preserved",
                error,
            )

    @staticmethod
    def as_dict(result: BatchResult) -> dict[str, object]:
        return {"status": result.status, "results": [asdict(entry) for entry in result.results]}
