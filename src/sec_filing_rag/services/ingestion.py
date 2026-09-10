from __future__ import annotations

import hashlib
import time
import uuid
from array import array
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from openai import OpenAI

from ..core.config import Settings
from ..domain.filings import (
    REQUIRED_ITEMS,
    Chunk,
    compatibility_key,
    extract_sections,
    make_chunks,
    safe_error,
    sanitize_filing_html,
)
from ..integrations.sec import AcquiredFiling
from ..repositories.corpus import IngestionRepository

EMBEDDING_BATCH_SIZE = 32


@dataclass(frozen=True)
class CorpusResult:
    run_id: uuid.UUID
    outcome: str
    corpus_version_id: uuid.UUID | None
    coverage: dict[str, str]
    section_count: int
    chunk_count: int
    search_document_count: int
    embedding_usage_status: str
    corpus_disposition: str
    error: str | None = None


class IngestionPipeline:
    """Build a corpus only from an acquisition already persisted by batch execution."""

    def __init__(self, settings: Settings, store: IngestionRepository, openai: OpenAI) -> None:
        self.settings, self.store, self.openai = settings, store, openai

    def _embed(self, run_id: uuid.UUID, chunks: Sequence[Chunk]) -> tuple[list[array[float]], str]:
        """Embed in bounded requests and retain only compact single-precision vectors."""
        started = time.monotonic()
        provider_started_at = datetime.now(UTC)
        vectors: list[array[float]] = []
        input_tokens = 0
        total_tokens = 0
        input_usage_complete = True
        total_usage_complete = True
        saw_response = False
        try:
            for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
                batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
                response = self.openai.embeddings.create(
                    model=self.settings.openai_embedding_model,
                    input=[chunk.text for chunk in batch],
                    dimensions=self.settings.openai_embedding_dimensions,
                )
                saw_response = True
                usage_object = getattr(response, "usage", None)
                batch_input_tokens = getattr(usage_object, "prompt_tokens", None)
                batch_total_tokens = getattr(usage_object, "total_tokens", None)
                if batch_input_tokens is None:
                    input_usage_complete = False
                else:
                    input_tokens += int(batch_input_tokens)
                if batch_total_tokens is None:
                    total_usage_complete = False
                else:
                    total_tokens += int(batch_total_tokens)

                data = response.data
                if len(data) != len(batch):
                    raise ValueError("embedding response dimension or count mismatch")
                ordered: list[array[float] | None] = [None] * len(batch)
                for entry in data:
                    index = getattr(entry, "index", None)
                    if type(index) is not int or not 0 <= index < len(batch):
                        raise ValueError("embedding response index mismatch")
                    if ordered[index] is not None:
                        raise ValueError("embedding response index mismatch")
                    vector = array("f", entry.embedding)
                    if len(vector) != self.settings.openai_embedding_dimensions:
                        raise ValueError("embedding response dimension or count mismatch")
                    ordered[index] = vector
                if any(vector is None for vector in ordered):
                    raise ValueError("embedding response index mismatch")
                vectors.extend(vector for vector in ordered if vector is not None)
                del data
                del response
        except Exception as provider_error:
            finished_at = datetime.now(UTC)
            self.store.record_embedding_usage(
                run_id,
                self.settings.openai_embedding_model,
                input_tokens=input_tokens if saw_response and input_usage_complete else None,
                total_tokens=total_tokens if saw_response and total_usage_complete else None,
                latency_ms=int((time.monotonic() - started) * 1000),
                provider_started_at=provider_started_at,
                provider_finished_at=finished_at,
                error=safe_error(provider_error, (self.settings.openai_api_key,)),
            )
            raise
        finished_at = datetime.now(UTC)
        reported = saw_response and input_usage_complete and total_usage_complete
        self.store.record_embedding_usage(
            run_id,
            self.settings.openai_embedding_model,
            input_tokens=input_tokens if reported else None,
            total_tokens=total_tokens if reported else None,
            latency_ms=int((time.monotonic() - started) * 1000),
            provider_started_at=provider_started_at,
            provider_finished_at=finished_at,
        )
        return vectors, "reported" if reported else "unavailable"

    def process_acquisition(
        self,
        *,
        item_id: uuid.UUID,
        ticker: str,
        acquired: AcquiredFiling,
        mode: str,
        kestra_execution_id: str | None,
    ) -> CorpusResult:
        provisional_key = compatibility_key(
            parser=self.settings.parser_version,
            chunker=self.settings.chunking_version,
            model=self.settings.openai_embedding_model,
            dimensions=self.settings.openai_embedding_dimensions,
            index=self.settings.index_version,
        )
        run_id, company_id = self.store.start_run(
            ticker, mode, provisional_key, kestra_execution_id, item_id
        )
        stage = "source-validation"
        try:
            self.store.stage(run_id, stage, "running", input_count=1)
            filing, document = acquired.filing, acquired.document
            if (
                document.media_type != "text/html"
                or document.sha256 != hashlib.sha256(document.content).hexdigest()
            ):
                raise ValueError("persisted acquisition failed source validation")
            key = compatibility_key(
                parser=self.settings.parser_version,
                chunker=self.settings.chunking_version,
                model=self.settings.openai_embedding_model,
                dimensions=self.settings.openai_embedding_dimensions,
                index=self.settings.index_version,
                source_checksum=document.sha256,
            )
            self.store.update_run_key(run_id, key)
            self.store.stage(run_id, stage, "succeeded", output_count=1)
            existing = self.store.ready_corpus(company_id, filing.accession, key)
            if existing is not None:
                active = bool(existing["is_active"])
                if mode == "latest" and not active:
                    self.store.activate_existing(company_id, existing["corpus_version_id"], run_id)
                    disposition, outcome = "promoted", "succeeded"
                else:
                    self.store.skip_run(run_id)
                    disposition, outcome = "unchanged", "skipped"
                return CorpusResult(
                    run_id,
                    outcome,
                    existing["corpus_version_id"],
                    existing["coverage"],
                    existing["section_count"],
                    existing["chunk_count"],
                    existing["search_document_count"],
                    existing["embedding_usage_status"],
                    disposition,
                )

            stage = "extraction"
            self.store.stage(run_id, stage, "running", input_count=1)
            narrative = sanitize_filing_html(
                document.content, max_chars=self.settings.max_filing_narrative_chars
            )
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
            self.store.stage(run_id, stage, "succeeded", output_count=len(sections))
            unusable = [
                item
                for item in REQUIRED_ITEMS
                if sections[item].status in {"failed", "not_assessed"}
            ]
            if unusable:
                raise ValueError(
                    "corpus extraction incomplete for required items: " + ", ".join(unusable)
                )

            stage = "embedding"
            flat_chunks = [chunk for item in REQUIRED_ITEMS for chunk in chunks[item]]
            if not flat_chunks:
                raise ValueError("corpus has no present sections to embed")
            self.store.stage(run_id, stage, "running", input_count=len(flat_chunks))
            vectors, usage_status = self._embed(run_id, flat_chunks)
            embeddings: dict[str, list[array[float]]] = {}
            cursor = 0
            for item in REQUIRED_ITEMS:
                embeddings[item] = vectors[cursor : cursor + len(chunks[item])]
                cursor += len(chunks[item])
            self.store.stage(run_id, stage, "succeeded", output_count=len(vectors))

            stage = "persistence"
            self.store.stage(run_id, stage, "running", input_count=len(flat_chunks))
            corpus_id = self.store.persist(
                run_id=run_id,
                company_id=company_id,
                ticker=ticker,
                cik=acquired.company.cik,
                name=acquired.company.name,
                acquired=acquired,
                sections=sections,
                chunks=chunks,
                embeddings=embeddings,
                key=key,
                parser=self.settings.parser_version,
                chunker=self.settings.chunking_version,
                model=self.settings.openai_embedding_model,
                dimensions=self.settings.openai_embedding_dimensions,
                index=self.settings.index_version,
                identity_hash=hashlib.sha256(self.settings.edgar_identity.encode()).hexdigest(),
                promote_default=mode == "latest",
            )
            coverage: dict[str, str] = {item: sections[item].status for item in REQUIRED_ITEMS}
            return CorpusResult(
                run_id,
                "succeeded",
                corpus_id,
                coverage,
                len(sections),
                len(flat_chunks),
                len(flat_chunks),
                usage_status,
                "activated" if mode == "latest" else "historical_ready",
            )
        except Exception as exc:
            error = safe_error(
                exc,
                (
                    self.settings.openai_api_key,
                    self.settings.ingestion_api_token,
                    self.settings.edgar_identity,
                ),
            )
            self.store.fail_run(run_id, stage, error)
            return CorpusResult(
                run_id, "failed", None, {}, 0, 0, 0, "failed", "previous_preserved", error
            )
