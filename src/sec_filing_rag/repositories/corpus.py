from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

from ..core.config import CompanyConfiguration
from ..domain.filings import REQUIRED_ITEMS, Chunk, ExtractedSection, sha256_bytes
from ..integrations.sec import AcquiredFiling
from .database import Database


class IngestionRepository:
    def __init__(self, database: Database | str) -> None:
        self.database = database if isinstance(database, Database) else Database(database)

    @contextmanager
    def connect(self):  # type: ignore[no-untyped-def]
        with self.database.transaction() as connection:
            yield connection

    def load_configuration(self, config: CompanyConfiguration, path: Path) -> None:
        version_id = uuid.uuid5(uuid.NAMESPACE_URL, config.sha256())
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO public.configuration_version(id,kind,path,normalized_json,sha256) "
                "VALUES (%s,'companies',%s,%s,%s) ON CONFLICT (sha256) DO NOTHING",
                (version_id, str(path), json.dumps(config.normalized()), config.sha256()),
            )
            for company in config.companies:
                connection.execute(
                    "INSERT INTO public.company(id,ticker,enabled,configuration_version_id) VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT (ticker) DO UPDATE SET enabled=excluded.enabled, "
                    "configuration_version_id=excluded.configuration_version_id, updated_at=now()",
                    (
                        uuid.uuid5(uuid.NAMESPACE_DNS, company.ticker),
                        company.ticker,
                        company.enabled,
                        version_id,
                    ),
                )

    def start_run(
        self,
        ticker: str,
        trigger: str,
        key: str,
        kestra_execution_id: str | None = None,
        item_id: uuid.UUID | None = None,
    ) -> tuple[uuid.UUID, uuid.UUID]:
        with self.connect() as connection:
            company = connection.execute(
                "SELECT id FROM public.company WHERE ticker=%s AND enabled", (ticker,)
            ).fetchone()
            if not company:
                raise ValueError("ticker is not enabled in company configuration")
            run_id = uuid.uuid4()
            connection.execute(
                "INSERT INTO public.ingestion_run"
                "(id,company_id,trigger,compatibility_key,kestra_execution_id,status,stage,started_at) "
                "VALUES (%s,%s,%s,%s,%s,'running','source-validation',now())",
                (run_id, company["id"], trigger, key, kestra_execution_id),
            )
            if item_id is not None:
                updated = connection.execute(
                    "UPDATE public.filing_batch_item SET ingestion_run_id=%s,updated_at=now() "
                    "WHERE id=%s AND ingestion_run_id IS NULL RETURNING id",
                    (run_id, item_id),
                ).fetchone()
                if updated is None:
                    raise ValueError("filing batch item already has an ingestion run")
            return run_id, company["id"]

    def record_embedding_usage(
        self,
        run_id: uuid.UUID,
        model: str,
        *,
        input_tokens: int | None,
        total_tokens: int | None,
        latency_ms: int,
        provider_started_at: Any,
        provider_finished_at: Any,
        error: str | None = None,
    ) -> None:
        status = "failed" if error else ("reported" if total_tokens is not None else "unavailable")
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO public.llm_usage"
                "(ingestion_run_id,operation,model,input_tokens,output_tokens,total_tokens,usage_status,"
                "normalized_status,latency_ms,provider_started_at,provider_finished_at) "
                "VALUES (%s,'embedding',%s,%s,NULL,%s,%s,%s,%s,%s,%s)",
                (
                    run_id,
                    model,
                    input_tokens,
                    total_tokens,
                    status,
                    error or "succeeded",
                    latency_ms,
                    provider_started_at,
                    provider_finished_at,
                ),
            )

    def update_run_key(self, run_id: uuid.UUID, key: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE public.ingestion_run SET compatibility_key=%s WHERE id=%s", (key, run_id)
            )

    def stage(
        self,
        run_id: uuid.UUID,
        stage: str,
        status: str,
        *,
        input_count: int | None = None,
        output_count: int | None = None,
        error: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO public.ingestion_stage"
                "(ingestion_run_id,stage,status,input_count,output_count,started_at,finished_at,safe_error) "
                "VALUES (%s,%s,%s,%s,%s,CASE WHEN %s='running' THEN now() END,"
                "CASE WHEN %s<>'running' THEN now() END,%s) "
                "ON CONFLICT (ingestion_run_id,stage,attempt) DO UPDATE SET status=excluded.status,"
                "input_count=COALESCE(excluded.input_count,public.ingestion_stage.input_count),"
                "output_count=COALESCE(excluded.output_count,public.ingestion_stage.output_count),"
                "finished_at=excluded.finished_at,safe_error=excluded.safe_error",
                (run_id, stage, status, input_count, output_count, status, status, error),
            )
            connection.execute(
                "UPDATE public.ingestion_run SET stage=%s WHERE id=%s", (stage, run_id)
            )

    def fail_run(self, run_id: uuid.UUID, stage: str, error: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO public.ingestion_stage(ingestion_run_id,stage,status,finished_at,safe_error) "
                "VALUES (%s,%s,'failed',now(),%s) ON CONFLICT (ingestion_run_id,stage,attempt) "
                "DO UPDATE SET status='failed',finished_at=now(),safe_error=excluded.safe_error",
                (run_id, stage, error),
            )
            connection.execute(
                "UPDATE public.ingestion_run SET status='failed',stage=%s,safe_error=%s,finished_at=now() "
                "WHERE id=%s",
                (stage, error, run_id),
            )
            if stage == "source-validation":
                connection.execute(
                    "UPDATE public.company c SET resolution_status='failed',safe_error=%s,updated_at=now() "
                    "FROM public.ingestion_run ir WHERE ir.id=%s AND c.id=ir.company_id",
                    (error, run_id),
                )

    def skip_run(self, run_id: uuid.UUID) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE public.ingestion_run SET status='skipped',stage='unchanged',finished_at=now() WHERE id=%s",
                (run_id,),
            )
            connection.execute(
                "INSERT INTO public.ingestion_stage(ingestion_run_id,stage,status,finished_at) "
                "VALUES (%s,'unchanged','skipped',now())",
                (run_id,),
            )

    def run_compatibility_key(self, run_id: uuid.UUID) -> str:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT compatibility_key FROM public.ingestion_run WHERE id=%s", (run_id,)
            ).fetchone()
        if row is None:
            raise ValueError("unknown ingestion run")
        return str(row["compatibility_key"])

    def ready_corpus(
        self, company_id: uuid.UUID, accession: str, key: str
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            corpus = connection.execute(
                "SELECT cv.id,COALESCE(max(lu.usage_status::text),'unavailable') AS usage,"
                "bool_or(COALESCE(ca.is_default,false)) AS is_active "
                "FROM silver.corpus_version cv JOIN silver.filing f ON f.id=cv.filing_id "
                "LEFT JOIN public.llm_usage lu ON lu.ingestion_run_id=cv.ingestion_run_id "
                "LEFT JOIN public.corpus_activation ca ON ca.corpus_version_id=cv.id "
                "WHERE f.company_id=%s AND f.accession=%s AND cv.compatibility_key=%s AND cv.status='ready' "
                "GROUP BY cv.id",
                (company_id, accession, key),
            ).fetchone()
            if not corpus:
                return None
            rows = connection.execute(
                "SELECT s.item,s.coverage_status::text AS coverage_status,count(DISTINCT ch.id)::integer AS chunks,"
                "count(DISTINCT gd.chunk_id)::integer AS documents FROM silver.section s "
                "LEFT JOIN silver.chunk ch ON ch.section_id=s.id "
                "LEFT JOIN gold.search_document gd ON gd.chunk_id=ch.id WHERE s.corpus_version_id=%s "
                "GROUP BY s.item,s.coverage_status",
                (corpus["id"],),
            ).fetchall()
            return {
                "corpus_version_id": corpus["id"],
                "coverage": {row["item"]: row["coverage_status"] for row in rows},
                "section_count": len(rows),
                "chunk_count": sum(row["chunks"] for row in rows),
                "search_document_count": sum(row["documents"] for row in rows),
                "embedding_usage_status": corpus["usage"],
                "is_active": corpus["is_active"],
            }

    def activate_existing(
        self, company_id: uuid.UUID, corpus_id: uuid.UUID, run_id: uuid.UUID
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "SELECT id FROM public.company WHERE id=%s FOR UPDATE", (company_id,)
            )
            connection.execute(
                "UPDATE public.corpus_activation SET is_default=false,deactivated_at=now() "
                "WHERE company_id=%s AND is_default",
                (company_id,),
            )
            connection.execute(
                "INSERT INTO public.corpus_activation(company_id,corpus_version_id,ingestion_run_id) "
                "VALUES (%s,%s,%s)",
                (company_id, corpus_id, run_id),
            )
            connection.execute(
                "UPDATE public.ingestion_run SET status='succeeded',stage='promoted',finished_at=now() WHERE id=%s",
                (run_id,),
            )

    def persist(
        self,
        *,
        run_id: uuid.UUID,
        company_id: uuid.UUID,
        ticker: str,
        cik: str,
        name: str,
        acquired: AcquiredFiling,
        sections: Mapping[str, ExtractedSection],
        chunks: Mapping[str, Sequence[Chunk]],
        embeddings: Mapping[str, Sequence[Sequence[float]]],
        key: str,
        parser: str,
        chunker: str,
        model: str,
        dimensions: int,
        index: str,
        identity_hash: str,
        promote_default: bool = True,
    ) -> uuid.UUID:
        """Persist, validate, and optionally activate a complete candidate atomically."""
        corpus_id = uuid.uuid4()
        # One transaction prevents an incomplete candidate from replacing the active corpus.
        with self.connect() as connection:
            connection.execute(
                "UPDATE public.company SET cik=%s,name=%s,resolution_status='resolved',safe_error=NULL,"
                "updated_at=now() WHERE id=%s",
                (cik, name, company_id),
            )
            filing = acquired.filing
            document = acquired.document
            company_snapshot_id = self._company_snapshot(connection, acquired, identity_hash)
            filing_snapshot_id = self._filing_snapshot(connection, acquired, company_snapshot_id)
            document_id = self._document(connection, acquired, filing_snapshot_id)
            filing_id = uuid.uuid4()
            connection.execute(
                "INSERT INTO silver.filing"
                "(id,company_id,edgar_company_snapshot_id,edgar_filing_snapshot_id,edgar_filing_document_id,cik,accession,form,primary_document,"
                "filing_date,report_date,source_url) VALUES (%s,%s,%s,%s,%s,%s,%s,'10-K',%s,%s,%s,%s) "
                "ON CONFLICT (cik,accession) DO NOTHING",
                (
                    filing_id,
                    company_id,
                    company_snapshot_id,
                    filing_snapshot_id,
                    document_id,
                    cik,
                    filing.accession,
                    filing.primary_document,
                    filing.filing_date,
                    filing.report_date,
                    document.source_url,
                ),
            )
            filing_row = connection.execute(
                "SELECT id FROM silver.filing WHERE cik=%s AND accession=%s",
                (cik, filing.accession),
            ).fetchone()
            filing_id = filing_row["id"]
            inserted = connection.execute(
                "INSERT INTO silver.corpus_version"
                "(id,filing_id,ingestion_run_id,compatibility_key,parser_version,chunking_version,"
                "embedding_model,embedding_dimensions,index_version,source_document_sha256,edgartools_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (filing_id,compatibility_key) DO NOTHING RETURNING id",
                (
                    corpus_id,
                    filing_id,
                    run_id,
                    key,
                    parser,
                    chunker,
                    model,
                    dimensions,
                    index,
                    document.sha256,
                    acquired.company.edgartools_version,
                ),
            ).fetchone()
            if inserted is None:
                existing = connection.execute(
                    "SELECT id FROM silver.corpus_version WHERE filing_id=%s "
                    "AND compatibility_key=%s AND status='ready'",
                    (filing_id, key),
                ).fetchone()
                if existing is None:
                    raise ValueError("compatible corpus exists but is not ready")
                corpus_id = uuid.UUID(str(existing["id"]))
                connection.execute(
                    "UPDATE public.ingestion_run SET status='skipped',stage='unchanged',"
                    "finished_at=now() WHERE id=%s",
                    (run_id,),
                )
                return corpus_id
            source_checksum = sha256_bytes(document.content)
            for item in REQUIRED_ITEMS:
                section = sections[item]
                section_id = uuid.uuid4()
                connection.execute(
                    "INSERT INTO silver.section"
                    "(id,corpus_version_id,filing_id,item,coverage_status,text_content,source_start,source_end,"
                    "source_anchor,sha256,parser_version,safe_error) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        section_id,
                        corpus_id,
                        filing_id,
                        item,
                        section.status,
                        section.text,
                        section.start,
                        section.end,
                        f"{filing.accession}:item-{item.lower()}",
                        sha256_bytes(section.text.encode()) if section.text else None,
                        parser,
                        section.error,
                    ),
                )
                item_vectors = embeddings[item]
                if len(chunks[item]) != len(item_vectors):
                    raise ValueError(f"Item {item} embedding count mismatch")
                for chunk, embedding in zip(chunks[item], item_vectors, strict=True):
                    provenance = {
                        "ticker": ticker,
                        "cik": cik,
                        "accession": filing.accession,
                        "item": item,
                        "source_document": filing.primary_document,
                        "source_url": document.source_url,
                        "edgar_filing_snapshot_id": str(filing_snapshot_id),
                        "edgar_filing_document_id": str(document_id),
                        "edgartools_version": acquired.company.edgartools_version,
                        "primary_document_url": document.source_url,
                        "source_document_checksum": source_checksum,
                        "source_checksum": source_checksum,
                        "source_start": chunk.start,
                        "source_end": chunk.end,
                        "anchor": chunk.citation,
                        "ordinal": chunk.ordinal,
                    }
                    connection.execute(
                        "INSERT INTO silver.chunk"
                        "(id,section_id,corpus_version_id,ordinal,text_content,source_start,source_end,"
                        "citation_handle,chunking_version,sha256) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            chunk.id,
                            section_id,
                            corpus_id,
                            chunk.ordinal,
                            chunk.text,
                            chunk.start,
                            chunk.end,
                            chunk.citation,
                            chunker,
                            chunk.sha256,
                        ),
                    )
                    connection.execute(
                        "INSERT INTO gold.search_document"
                        "(chunk_id,corpus_version_id,company_id,filing_id,item,text_content,citation_handle,"
                        "provenance,embedding,embedding_model,embedding_dimensions,lexical_document) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            chunk.id,
                            corpus_id,
                            company_id,
                            filing_id,
                            item,
                            chunk.text,
                            chunk.citation,
                            json.dumps(provenance),
                            list(embedding),
                            model,
                            dimensions,
                            chunk.text,
                        ),
                    )
            self._validate_candidate(connection, corpus_id, model, dimensions)
            connection.execute(
                "SELECT id FROM public.company WHERE id=%s FOR UPDATE", (company_id,)
            )
            connection.execute(
                "UPDATE silver.corpus_version SET status='ready',ready_at=now() WHERE id=%s",
                (corpus_id,),
            )
            if promote_default:
                connection.execute(
                    "UPDATE public.corpus_activation SET is_default=false,deactivated_at=now() "
                    "WHERE company_id=%s AND is_default",
                    (company_id,),
                )
                connection.execute(
                    "INSERT INTO public.corpus_activation(company_id,corpus_version_id,ingestion_run_id) "
                    "VALUES (%s,%s,%s)",
                    (company_id, corpus_id, run_id),
                )
            total_chunks = sum(len(chunks[item]) for item in REQUIRED_ITEMS)
            connection.execute(
                "UPDATE public.ingestion_run SET status='succeeded',stage='promoted',section_count=%s,"
                "chunk_count=%s,finished_at=now() WHERE id=%s",
                (len(REQUIRED_ITEMS), total_chunks, run_id),
            )
            connection.execute(
                "UPDATE public.ingestion_stage SET status='succeeded',output_count=%s,finished_at=now() "
                "WHERE ingestion_run_id=%s AND stage='persistence'",
                (total_chunks, run_id),
            )
        return corpus_id

    def _validate_candidate(
        self, connection: Any, corpus_id: uuid.UUID, model: str, dimensions: int
    ) -> None:
        # Redundant lineage validation is intentional: promotion fails closed at the DB boundary.
        rows = connection.execute(
            "SELECT s.item,s.coverage_status::text AS status,s.safe_error,count(DISTINCT ch.id)::integer AS chunks,"
            "count(DISTINCT gd.chunk_id)::integer AS documents,"
            "count(DISTINCT ch.id) FILTER (WHERE ch.source_end>ch.source_start "
            "AND ch.citation_handle<>'' AND ch.text_content<>'')::integer AS valid_chunks,"
            "count(DISTINCT gd.chunk_id) FILTER (WHERE gd.lexical_document IS NOT NULL "
            "AND gd.lexical_document=gd.text_content AND gd.text_content=ch.text_content "
            "AND gd.citation_handle=ch.citation_handle AND gd.embedding_model=%s "
            "AND gd.embedding_dimensions=%s AND gd.provenance ?& "
            "ARRAY['ticker','cik','accession','item','source_document','source_url',"
            "'source_checksum','edgar_filing_snapshot_id','edgar_filing_document_id',"
            "'edgartools_version','primary_document_url','source_document_checksum',"
            "'source_start','source_end','anchor','ordinal'] "
            "AND gd.provenance->>'anchor'=ch.citation_handle "
            "AND (gd.provenance->>'source_start')::integer=ch.source_start "
            "AND (gd.provenance->>'source_end')::integer=ch.source_end)::integer AS valid_gold "
            "FROM silver.section s LEFT JOIN silver.chunk ch ON ch.section_id=s.id "
            "LEFT JOIN gold.search_document gd ON gd.chunk_id=ch.id WHERE s.corpus_version_id=%s "
            "GROUP BY s.item,s.coverage_status,s.safe_error",
            (model, dimensions, corpus_id),
        ).fetchall()
        if len(rows) != len(REQUIRED_ITEMS) or {row["item"] for row in rows} != set(REQUIRED_ITEMS):
            raise ValueError("corpus promotion requires exactly one coverage row per required item")
        for row in rows:
            if row["status"] in {"failed", "not_assessed"}:
                raise ValueError(f"Item {row['item']} has incomplete coverage")
            if row["status"] == "present" and (
                row["chunks"] <= 0
                or row["chunks"] != row["documents"]
                or row["chunks"] != row["valid_chunks"]
                or row["chunks"] != row["valid_gold"]
            ):
                raise ValueError(f"Item {row['item']} has inconsistent retrieval records")
            if row["status"] == "legitimately_absent" and (row["chunks"] or not row["safe_error"]):
                raise ValueError(f"Item {row['item']} has invalid absent coverage")

    def _company_snapshot(
        self, connection: Any, acquired: AcquiredFiling, identity_hash: str
    ) -> uuid.UUID:
        company = acquired.company
        metadata = {
            "requested_ticker": company.requested_ticker,
            "cik": company.cik,
            "name": company.name,
            "tickers": list(company.tickers),
            "exchanges": list(company.exchanges),
            "sic": company.sic,
            "industry": company.industry,
            "fiscal_year_end": company.fiscal_year_end,
            "filer_type": company.filer_type,
            "is_company": company.is_company,
            "edgartools_version": company.edgartools_version,
        }
        # Bronze identity hashes canonical primitive metadata, never provider SDK objects.
        digest = sha256_bytes(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode())
        row_id = uuid.uuid4()
        connection.execute(
            "INSERT INTO bronze.edgar_company_snapshot"
            "(id,requested_ticker,cik,legal_name,tickers,exchanges,sic,industry,fiscal_year_end,filer_type,"
            "is_company,edgartools_version,edgar_identity_hash,canonical_metadata_sha256) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (canonical_metadata_sha256) DO NOTHING",
            (
                row_id,
                company.requested_ticker,
                company.cik,
                company.name,
                list(company.tickers),
                list(company.exchanges),
                company.sic,
                company.industry,
                company.fiscal_year_end,
                company.filer_type,
                company.is_company,
                company.edgartools_version,
                identity_hash,
                digest,
            ),
        )
        result = connection.execute(
            "SELECT id FROM bronze.edgar_company_snapshot WHERE canonical_metadata_sha256=%s",
            (digest,),
        ).fetchone()["id"]
        return uuid.UUID(str(result))

    def _filing_snapshot(
        self, connection: Any, acquired: AcquiredFiling, company_snapshot_id: uuid.UUID
    ) -> uuid.UUID:
        filing = acquired.filing
        metadata = {
            "accession": filing.accession,
            "form": filing.form,
            "filing_date": filing.filing_date.isoformat(),
            "report_date": filing.report_date.isoformat(),
            "acceptance_datetime": filing.acceptance_datetime.isoformat()
            if filing.acceptance_datetime
            else None,
            "act": filing.act,
            "file_number": filing.file_number,
            "size": filing.size,
            "is_xbrl": filing.is_xbrl,
            "is_inline_xbrl": filing.is_inline_xbrl,
            "primary_document": filing.primary_document,
            "primary_document_description": filing.primary_document_description,
            "homepage_url": filing.homepage_url,
            "filing_url": filing.filing_url,
            "text_url": filing.text_url,
        }
        digest = sha256_bytes(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode())
        row_id = uuid.uuid4()
        connection.execute(
            "INSERT INTO bronze.edgar_filing_snapshot"
            "(id,company_snapshot_id,accession,form,filing_date,report_date,acceptance_datetime,act,file_number,"
            "submission_size,is_xbrl,is_inline_xbrl,primary_document,primary_document_description,homepage_url,"
            "filing_url,text_url,edgartools_version,canonical_metadata_sha256) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (canonical_metadata_sha256) DO NOTHING",
            (
                row_id,
                company_snapshot_id,
                filing.accession,
                filing.form,
                filing.filing_date,
                filing.report_date,
                filing.acceptance_datetime,
                filing.act,
                filing.file_number,
                filing.size,
                filing.is_xbrl,
                filing.is_inline_xbrl,
                filing.primary_document,
                filing.primary_document_description,
                filing.homepage_url,
                filing.filing_url,
                filing.text_url,
                acquired.company.edgartools_version,
                digest,
            ),
        )
        result = connection.execute(
            "SELECT id FROM bronze.edgar_filing_snapshot WHERE canonical_metadata_sha256=%s",
            (digest,),
        ).fetchone()["id"]
        return uuid.UUID(str(result))

    def _document(
        self, connection: Any, acquired: AcquiredFiling, filing_snapshot_id: uuid.UUID
    ) -> uuid.UUID:
        document = acquired.document
        # This checksum covers the exact UTF-8 HTML bytes acquired and parsed.
        row_id = uuid.uuid4()
        connection.execute(
            "INSERT INTO bronze.edgar_filing_document"
            "(id,filing_snapshot_id,document_name,document_type,sequence_number,description,source_url,content,"
            "media_type,content_encoding,content_length,content_sha256,edgartools_version) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (content_sha256) DO NOTHING",
            (
                row_id,
                filing_snapshot_id,
                document.name,
                document.document_type,
                document.sequence,
                document.description,
                document.source_url,
                document.content,
                document.media_type,
                document.content_encoding,
                len(document.content),
                document.sha256,
                acquired.company.edgartools_version,
            ),
        )
        result = connection.execute(
            "SELECT id FROM bronze.edgar_filing_document WHERE content_sha256=%s",
            (document.sha256,),
        ).fetchone()["id"]
        return uuid.UUID(str(result))


def migration_files() -> list[Path]:
    # Both the source checkout and runtime image keep assets in the working directory.
    root = Path.cwd() / "migrations" / "versions"
    paths = sorted(root.glob("*.sql"))
    if not paths:
        raise RuntimeError(
            "No migration SQL files found; run from the application root containing "
            "migrations/versions (the container uses /app)."
        )
    return paths


class AppliedMigrationChangedError(RuntimeError):
    def __init__(self, name: str, stored_sha256: str, file_sha256: str) -> None:
        self.name = name
        self.stored_sha256 = stored_sha256
        self.file_sha256 = file_sha256
        super().__init__(
            f"Migration integrity check failed for {name}: "
            f"stored database SHA-256={stored_sha256}; current file SHA-256={file_sha256}. "
            "Applied migrations are immutable, so the transaction was rolled back and no "
            "migration changes were committed. This repository uses a fresh-start-only schema. "
            "Follow docs/operations.md#reset-only-the-application-database-destructive. "
            "Do not edit public.schema_migration manually."
        )


def apply_migrations(database_url: str) -> None:
    paths = migration_files()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS public.schema_migration "
            "(name text PRIMARY KEY, sha256 char(64) NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        for path in paths:
            body = path.read_bytes()
            digest = sha256_bytes(body)
            existing = connection.execute(
                "SELECT sha256 FROM public.schema_migration WHERE name=%s", (path.name,)
            ).fetchone()
            if existing:
                if existing[0] != digest:
                    raise AppliedMigrationChangedError(path.name, existing[0], digest)
                continue
            connection.execute(sql.SQL(body.decode()))
            connection.execute(
                "INSERT INTO public.schema_migration(name,sha256) VALUES (%s,%s)",
                (path.name, digest),
            )
