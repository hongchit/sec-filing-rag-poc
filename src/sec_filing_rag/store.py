from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .config import CompanyConfiguration
from .domain import Chunk, ExtractedSection, FilingCandidate, sha256_bytes
from .sec import Fetched


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
                connection.execute("SELECT 1")
            return True
        except psycopg.Error:
            return False

    def load_configuration(self, config: CompanyConfiguration, path: Path) -> None:
        version_id = uuid.uuid5(uuid.NAMESPACE_URL, config.sha256())
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO public.configuration_version(id,kind,path,normalized_json,sha256) VALUES (%s,'companies',%s,%s,%s) ON CONFLICT (sha256) DO NOTHING",
                (version_id, str(path), json.dumps(config.normalized()), config.sha256()),
            )
            for company in config.companies:
                connection.execute(
                    "INSERT INTO public.company(id,ticker,enabled,configuration_version_id) VALUES (%s,%s,%s,%s) ON CONFLICT (ticker) DO UPDATE SET enabled=excluded.enabled, configuration_version_id=excluded.configuration_version_id, updated_at=now()",
                    (uuid.uuid5(uuid.NAMESPACE_DNS, company.ticker), company.ticker, company.enabled, version_id),
                )

    def start_run(self, ticker: str, item: str, trigger: str, key: str) -> tuple[uuid.UUID, uuid.UUID]:
        with self.connect() as connection:
            company = connection.execute("SELECT id FROM public.company WHERE ticker=%s AND enabled", (ticker,)).fetchone()
            if not company:
                raise ValueError("ticker is not enabled in company configuration")
            run_id = uuid.uuid4()
            connection.execute("INSERT INTO public.ingestion_run(id,company_id,requested_item,trigger,compatibility_key,status,stage,started_at) VALUES (%s,%s,%s,%s,%s,'running','resolve',now())", (run_id, company["id"], item, trigger, key))
            return run_id, company["id"]

    def fail_run(self, run_id: uuid.UUID, stage: str, error: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE public.ingestion_run SET status='failed',stage=%s,safe_error=%s,finished_at=now() WHERE id=%s", (stage, error, run_id))

    def persist(self, *, run_id: uuid.UUID, company_id: uuid.UUID, ticker: str, cik: str, name: str,
                ticker_fetch: Fetched, submission_fetch: Fetched, submission: dict[str, Any], document: Fetched,
                filing: FilingCandidate, section: ExtractedSection, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]],
                key: str, parser: str, chunker: str, model: str, dimensions: int, index: str,
                usage: tuple[int | None, int | None, int | None, str], user_agent_hash: str) -> uuid.UUID:
        ids = [uuid.uuid4() for _ in range(6)]
        ticker_id, submission_id, document_id, filing_id, corpus_id, section_id = ids
        with self.connect() as connection:
            connection.execute("UPDATE public.company SET cik=%s,name=%s,resolution_status='resolved',safe_error=NULL,updated_at=now() WHERE id=%s", (cik, name, company_id))
            common = (user_agent_hash,)
            connection.execute("INSERT INTO bronze.sec_ticker_snapshot(id,payload,source_url,user_agent_hash,fetched_at,http_status,etag,last_modified,sha256) VALUES (%s,%s,%s,%s,now(),%s,%s,%s,%s) ON CONFLICT (sha256) DO NOTHING", (ticker_id, ticker_fetch.body.decode(), ticker_fetch.url, *common, ticker_fetch.status, ticker_fetch.headers.get("etag"), ticker_fetch.headers.get("last-modified"), sha256_bytes(ticker_fetch.body)))
            row = connection.execute("SELECT id FROM bronze.sec_ticker_snapshot WHERE sha256=%s", (sha256_bytes(ticker_fetch.body),)).fetchone(); ticker_id = row["id"]
            connection.execute("INSERT INTO bronze.sec_submission(id,cik,payload,source_url,user_agent_hash,fetched_at,http_status,etag,last_modified,sha256) VALUES (%s,%s,%s,%s,%s,now(),%s,%s,%s,%s) ON CONFLICT (sha256) DO NOTHING", (submission_id,cik,json.dumps(submission),submission_fetch.url,*common,submission_fetch.status,submission_fetch.headers.get("etag"),submission_fetch.headers.get("last-modified"),sha256_bytes(submission_fetch.body)))
            row = connection.execute("SELECT id FROM bronze.sec_submission WHERE sha256=%s", (sha256_bytes(submission_fetch.body),)).fetchone(); submission_id = row["id"]
            connection.execute("INSERT INTO bronze.sec_document(id,cik,accession,document_name,source_url,content,media_type,content_length,user_agent_hash,fetched_at,http_status,etag,last_modified,sha256) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,%s,%s) ON CONFLICT (sha256) DO NOTHING", (document_id,cik,filing.accession,filing.primary_document,document.url,document.body,document.headers.get("content-type","text/html"),len(document.body),*common,document.status,document.headers.get("etag"),document.headers.get("last-modified"),sha256_bytes(document.body)))
            row = connection.execute("SELECT id FROM bronze.sec_document WHERE sha256=%s", (sha256_bytes(document.body),)).fetchone(); document_id = row["id"]
            connection.execute("INSERT INTO silver.filing(id,company_id,ticker_snapshot_id,submission_id,document_id,cik,accession,form,primary_document,filing_date,report_date,source_url) VALUES (%s,%s,%s,%s,%s,%s,%s,'10-K',%s,%s,%s,%s) ON CONFLICT (cik,accession) DO NOTHING", (filing_id,company_id,ticker_id,submission_id,document_id,cik,filing.accession,filing.primary_document,filing.filing_date,filing.report_date,document.url))
            row = connection.execute("SELECT id FROM silver.filing WHERE cik=%s AND accession=%s", (cik,filing.accession)).fetchone(); filing_id = row["id"]
            existing = connection.execute("SELECT id,status FROM silver.corpus_version WHERE filing_id=%s AND compatibility_key=%s", (filing_id,key)).fetchone()
            if existing and existing["status"] == "ready":
                connection.execute("UPDATE public.ingestion_run SET status='skipped',stage='unchanged',finished_at=now() WHERE id=%s", (run_id,))
                return uuid.UUID(str(existing["id"]))
            connection.execute("INSERT INTO silver.corpus_version(id,filing_id,ingestion_run_id,compatibility_key,parser_version,chunking_version,embedding_model,embedding_dimensions,index_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", (corpus_id,filing_id,run_id,key,parser,chunker,model,dimensions,index))
            connection.execute("INSERT INTO silver.section(id,corpus_version_id,filing_id,item,coverage_status,text_content,source_start,source_end,source_anchor,sha256,parser_version,safe_error) VALUES (%s,%s,%s,'1A',%s,%s,%s,%s,%s,%s,%s,%s)", (section_id,corpus_id,filing_id,section.status,section.text,section.start,section.end,f"{filing.accession}:item-1a",sha256_bytes(section.text.encode()) if section.text else None,parser,section.error))
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                connection.execute("INSERT INTO silver.chunk(id,section_id,corpus_version_id,ordinal,text_content,source_start,source_end,citation_handle,chunking_version,sha256) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (chunk.id,section_id,corpus_id,chunk.ordinal,chunk.text,chunk.start,chunk.end,chunk.citation,chunker,chunk.sha256))
                connection.execute("INSERT INTO gold.search_document(chunk_id,corpus_version_id,company_id,filing_id,item,text_content,citation_handle,provenance,embedding,embedding_model,embedding_dimensions) VALUES (%s,%s,%s,%s,'1A',%s,%s,%s,%s,%s,%s)", (chunk.id,corpus_id,company_id,filing_id,chunk.text,chunk.citation,json.dumps({"ticker":ticker,"accession":filing.accession,"url":document.url}),list(embedding),model,dimensions))
            connection.execute("INSERT INTO public.llm_usage(ingestion_run_id,operation,model,input_tokens,output_tokens,total_tokens,usage_status,normalized_status) VALUES (%s,'embedding',%s,%s,%s,%s,%s,'succeeded')", (run_id,model,*usage))
            count = connection.execute("SELECT count(*) AS n FROM gold.search_document WHERE corpus_version_id=%s AND embedding_dimensions=%s", (corpus_id,dimensions)).fetchone()["n"]
            if section.status != "present" or count != len(chunks) or count == 0:
                raise ValueError("corpus promotion validation failed")
            connection.execute("SELECT id FROM public.company WHERE id=%s FOR UPDATE", (company_id,))
            connection.execute("UPDATE silver.corpus_version SET status='ready',ready_at=now() WHERE id=%s", (corpus_id,))
            connection.execute("UPDATE public.corpus_activation SET active=false,deactivated_at=now() WHERE company_id=%s AND active", (company_id,))
            connection.execute("INSERT INTO public.corpus_activation(company_id,corpus_version_id,ingestion_run_id) VALUES (%s,%s,%s)", (company_id,corpus_id,run_id))
            connection.execute("UPDATE public.ingestion_run SET status='succeeded',stage='promoted',section_count=1,chunk_count=%s,finished_at=now() WHERE id=%s", (len(chunks),run_id))
        return corpus_id


def apply_migrations(database_url: str, directory: Path = Path("migrations/versions")) -> None:
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS public.schema_migration "
            "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        for path in sorted(directory.glob("[0-9]*.sql")):
            if path.name.endswith(".down.sql"):
                continue
            applied = connection.execute(
                "SELECT 1 FROM public.schema_migration WHERE name=%s", (path.name,)
            ).fetchone()
            if applied:
                continue
            connection.execute(sql.SQL(path.read_text(encoding="utf-8")))
            connection.execute("INSERT INTO public.schema_migration(name) VALUES (%s)", (path.name,))
