from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass

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

    def process_acquisition(
        self, *, ticker: str, acquired: AcquiredFiling, mode: str, kestra_execution_id: str | None
    ) -> CorpusResult:
        provisional_key = compatibility_key(
            parser=self.settings.parser_version,
            chunker=self.settings.chunking_version,
            model=self.settings.openai_embedding_model,
            dimensions=self.settings.openai_embedding_dimensions,
            index=self.settings.index_version,
        )
        run_id, company_id = self.store.start_run(ticker, mode, provisional_key, kestra_execution_id)
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
                item for item in REQUIRED_ITEMS if sections[item].status in {"failed", "not_assessed"}
            ]
            if unusable:
                raise ValueError("corpus extraction incomplete for required items: " + ", ".join(unusable))

            stage = "embedding"
            flat_chunks = [chunk for item in REQUIRED_ITEMS for chunk in chunks[item]]
            if not flat_chunks:
                raise ValueError("corpus has no present sections to embed")
            self.store.stage(run_id, stage, "running", input_count=len(flat_chunks))
            started = time.monotonic()
            response = self.openai.embeddings.create(
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
            prompt_tokens, total_tokens = (
                getattr(usage_object, "prompt_tokens", None),
                getattr(usage_object, "total_tokens", None),
            )
            usage = (
                prompt_tokens,
                None,
                total_tokens,
                "reported" if total_tokens is not None else "unavailable",
                int((time.monotonic() - started) * 1000),
            )
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
                usage=usage,
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
                usage[3],
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
            return CorpusResult(run_id, "failed", None, {}, 0, 0, 0, "failed", "previous_preserved", error)
