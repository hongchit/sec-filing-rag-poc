from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .config import CompanyConfiguration
from .domain import REQUIRED_ITEMS, Chunk, ExtractedSection, sha256_bytes
from .sec import AcquiredFiling


class Store:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    @contextmanager
    def connect(self):  # type: ignore[no-untyped-def]
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            yield connection

    def ready(self) -> bool:
        try:
            with self.connect() as connection:
                relations = connection.execute(
                    "SELECT to_regclass('public.schema_migration') AS schema_migration,"
                    "to_regclass('public.company') AS company,"
                    "to_regclass('silver.corpus_version') AS corpus_version,"
                    "to_regclass('gold.search_document') AS search_document"
                ).fetchone()
                if relations is None or any(value is None for value in relations.values()):
                    return False
                migration = connection.execute(
                    "SELECT 1 FROM public.schema_migration WHERE name=%s",
                    ("0001_schema.sql",),
                ).fetchone()
                return migration is not None
        except psycopg.Error:
            return False

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

    def validate_preparation_callback(
        self, request_id: uuid.UUID, ticker: str, requested_year: int, accession: str
    ) -> None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT pr.id FROM public.preparation_request pr JOIN public.company c ON c.id=pr.company_id "
                "WHERE pr.id=%s AND c.ticker=%s AND pr.requested_year=%s "
                "AND pr.selected_accession=%s AND pr.status IN ('submitted','running') FOR UPDATE",
                (request_id, ticker, requested_year, accession),
            ).fetchone()
            if row is None:
                raise ValueError("historical preparation callback does not match an active request")
            connection.execute(
                "UPDATE public.preparation_request SET status='running',updated_at=now() WHERE id=%s",
                (request_id,),
            )

    def start_run(
        self,
        ticker: str,
        item: str,
        trigger: str,
        key: str,
        preparation_request_id: uuid.UUID | None = None,
        kestra_execution_id: str | None = None,
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
                "(id,company_id,requested_item,trigger,compatibility_key,preparation_request_id,"
                "kestra_execution_id,status,stage,started_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'running','resolve',now())",
                (run_id, company["id"], item, trigger, key, preparation_request_id, kestra_execution_id),
            )
            return run_id, company["id"]

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
            connection.execute("UPDATE public.ingestion_run SET stage=%s WHERE id=%s", (stage, run_id))

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
            if stage == "resolve":
                connection.execute(
                    "UPDATE public.company c SET resolution_status='failed',safe_error=%s,updated_at=now() "
                    "FROM public.ingestion_run ir WHERE ir.id=%s AND c.id=ir.company_id",
                    (error, run_id),
                )

    def complete_preparation(self, request_id: uuid.UUID, corpus_id: uuid.UUID) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE public.preparation_request SET status='succeeded',corpus_version_id=%s,"
                "finished_at=now(),updated_at=now() WHERE id=%s",
                (corpus_id, request_id),
            )

    def fail_preparation(self, request_id: uuid.UUID, error: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE public.preparation_request SET status='failed',safe_error=%s,"
                "finished_at=now(),updated_at=now() WHERE id=%s",
                (error, request_id),
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

    def ready_corpus(self, company_id: uuid.UUID, accession: str, key: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            corpus = connection.execute(
                "SELECT cv.id,COALESCE(max(lu.usage_status::text),'unavailable') AS usage "
                "FROM silver.corpus_version cv JOIN silver.filing f ON f.id=cv.filing_id "
                "LEFT JOIN public.llm_usage lu ON lu.ingestion_run_id=cv.ingestion_run_id "
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
            }

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
        usage: tuple[int | None, int | None, int | None, str, int],
        identity_hash: str,
        promote_default: bool = True,
        preparation_request_id: uuid.UUID | None = None,
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
                "SELECT id FROM silver.filing WHERE cik=%s AND accession=%s", (cik, filing.accession)
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
                if preparation_request_id is not None:
                    connection.execute(
                        "UPDATE public.preparation_request SET status='succeeded',corpus_version_id=%s,"
                        "finished_at=now(),updated_at=now() WHERE id=%s",
                        (corpus_id, preparation_request_id),
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
            connection.execute(
                "INSERT INTO public.llm_usage"
                "(ingestion_run_id,operation,model,input_tokens,output_tokens,total_tokens,usage_status,"
                "normalized_status,latency_ms) VALUES (%s,'embedding',%s,%s,%s,%s,%s,'succeeded',%s)",
                (run_id, model, *usage),
            )
            self._validate_candidate(connection, corpus_id, model, dimensions)
            connection.execute("SELECT id FROM public.company WHERE id=%s FOR UPDATE", (company_id,))
            connection.execute(
                "UPDATE silver.corpus_version SET status='ready',ready_at=now() WHERE id=%s", (corpus_id,)
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
            if preparation_request_id is not None:
                connection.execute(
                    "UPDATE public.preparation_request SET status='succeeded',corpus_version_id=%s,"
                    "finished_at=now(),updated_at=now() WHERE id=%s",
                    (corpus_id, preparation_request_id),
                )
            total_chunks = sum(len(chunks[item]) for item in REQUIRED_ITEMS)
            connection.execute(
                "UPDATE public.ingestion_run SET status='succeeded',stage='promoted',section_count=%s,"
                "chunk_count=%s,finished_at=now() WHERE id=%s",
                (len(REQUIRED_ITEMS), total_chunks, run_id),
            )
            connection.execute(
                "UPDATE public.ingestion_stage SET status='succeeded',output_count=%s,finished_at=now() "
                "WHERE ingestion_run_id=%s AND stage='persist-promote'",
                (total_chunks, run_id),
            )
        return corpus_id

    def _validate_candidate(self, connection: Any, corpus_id: uuid.UUID, model: str, dimensions: int) -> None:
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

    def _company_snapshot(self, connection: Any, acquired: AcquiredFiling, identity_hash: str) -> uuid.UUID:
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
            "SELECT id FROM bronze.edgar_company_snapshot WHERE canonical_metadata_sha256=%s", (digest,)
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
            "SELECT id FROM bronze.edgar_filing_snapshot WHERE canonical_metadata_sha256=%s", (digest,)
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
            "SELECT id FROM bronze.edgar_filing_document WHERE content_sha256=%s", (document.sha256,)
        ).fetchone()["id"]
        return uuid.UUID(str(result))

    def companies(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    "SELECT c.ticker,c.enabled,c.cik,c.name,c.resolution_status::text AS resolution_status,"
                    "c.safe_error,f.accession,f.filing_date,cv.status::text AS corpus_status,cv.ready_at,"
                    "COALESCE(ir.status::text,'pending') AS latest_run_status "
                    "FROM public.company c LEFT JOIN LATERAL (SELECT * FROM public.ingestion_run r "
                    "WHERE r.company_id=c.id ORDER BY r.created_at DESC LIMIT 1) ir ON true "
                    "LEFT JOIN public.corpus_activation ca ON ca.company_id=c.id AND ca.is_default "
                    "LEFT JOIN silver.corpus_version cv ON cv.id=ca.corpus_version_id "
                    "LEFT JOIN silver.filing f ON f.id=cv.filing_id ORDER BY c.ticker"
                ).fetchall()
            )

    def company_status(self, ticker: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            company = connection.execute(
                "SELECT c.id,c.ticker,c.enabled,c.cik,c.name,c.resolution_status::text AS resolution_status,"
                "c.safe_error FROM public.company c WHERE c.ticker=%s",
                (ticker,),
            ).fetchone()
            if not company:
                return None
            active = connection.execute(
                "SELECT cv.id AS corpus_version_id,cv.ready_at,cv.embedding_model,cv.embedding_dimensions,"
                "f.accession,f.filing_date,f.report_date,f.source_url,lu.usage_status::text AS embedding_usage_status "
                "FROM public.corpus_activation ca JOIN silver.corpus_version cv ON cv.id=ca.corpus_version_id "
                "JOIN silver.filing f ON f.id=cv.filing_id LEFT JOIN public.llm_usage lu "
                "ON lu.ingestion_run_id=cv.ingestion_run_id AND lu.operation='embedding' "
                "WHERE ca.company_id=%s AND ca.is_default",
                (company["id"],),
            ).fetchone()
            coverage: list[dict[str, Any]] = []
            if active:
                rows = connection.execute(
                    "SELECT s.item,s.coverage_status::text AS status,s.safe_error,"
                    "count(DISTINCT ch.id)::integer AS chunk_count,"
                    "count(DISTINCT gd.chunk_id)::integer AS search_document_count "
                    "FROM silver.section s LEFT JOIN silver.chunk ch ON ch.section_id=s.id "
                    "LEFT JOIN gold.search_document gd ON gd.chunk_id=ch.id WHERE s.corpus_version_id=%s "
                    "GROUP BY s.item,s.coverage_status,s.safe_error",
                    (active["corpus_version_id"],),
                ).fetchall()
                by_item = {row["item"]: dict(row) for row in rows}
                coverage = [by_item[item] for item in REQUIRED_ITEMS if item in by_item]
            latest = connection.execute(
                "SELECT id AS run_id,status::text AS status,stage,section_count,chunk_count,safe_error,"
                "started_at,finished_at FROM public.ingestion_run WHERE company_id=%s "
                "ORDER BY created_at DESC LIMIT 1",
                (company["id"],),
            ).fetchone()
            result = dict(company)
            result.pop("id")
            result["active_corpus"] = dict(active) if active else None
            result["latest_default_corpus"] = dict(active) if active else None
            historical = connection.execute(
                "SELECT cv.id AS corpus_version_id,cv.ready_at,f.accession,f.report_date,f.filing_date "
                "FROM silver.corpus_version cv JOIN silver.filing f ON f.id=cv.filing_id "
                "WHERE f.company_id=%s AND cv.status='ready' ORDER BY f.report_date DESC,f.filing_date DESC",
                (company["id"],),
            ).fetchall()
            preparations = connection.execute(
                "SELECT id AS request_id,requested_year,selected_accession,selected_fiscal_year,"
                "confirmation_state::text AS confirmation_state,status::text AS status,"
                "kestra_execution_id,corpus_version_id,safe_error,created_at,updated_at "
                "FROM public.preparation_request WHERE company_id=%s ORDER BY created_at DESC",
                (company["id"],),
            ).fetchall()
            result["historical_corpora"] = [dict(row) for row in historical]
            result["preparation_requests"] = [dict(row) for row in preparations]
            result["coverage"] = coverage
            result["latest_run"] = dict(latest) if latest else None
            return result


def migration_files() -> list[Path]:
    root = Path(__file__).resolve().parents[2] / "migrations" / "versions"
    return sorted(root.glob("*.sql"))


def apply_migrations(database_url: str) -> None:
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS public.schema_migration "
            "(name text PRIMARY KEY, sha256 char(64) NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        for path in migration_files():
            body = path.read_bytes()
            digest = sha256_bytes(body)
            existing = connection.execute(
                "SELECT sha256 FROM public.schema_migration WHERE name=%s", (path.name,)
            ).fetchone()
            if existing:
                if existing[0] != digest:
                    raise RuntimeError(f"applied migration changed: {path.name}")
                continue
            connection.execute(sql.SQL(body.decode()))
            connection.execute(
                "INSERT INTO public.schema_migration(name,sha256) VALUES (%s,%s)", (path.name, digest)
            )
