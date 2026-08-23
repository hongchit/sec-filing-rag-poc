from __future__ import annotations

from typing import Any

from ..domain.filings import REQUIRED_ITEMS
from .database import Database


class CompanyRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list(self) -> list[dict[str, Any]]:
        with self.database.transaction() as connection:
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

    def status(self, ticker: str) -> dict[str, Any] | None:
        with self.database.transaction() as connection:
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
            historical = connection.execute(
                "SELECT cv.id AS corpus_version_id,cv.ready_at,f.accession,f.report_date,f.filing_date "
                "FROM silver.corpus_version cv JOIN silver.filing f ON f.id=cv.filing_id "
                "LEFT JOIN public.corpus_activation ca ON ca.corpus_version_id=cv.id AND ca.is_default "
                "WHERE f.company_id=%s AND cv.status='ready' AND ca.id IS NULL "
                "ORDER BY f.report_date DESC,f.filing_date DESC",
                (company["id"],),
            ).fetchall()
            result["historical_corpora"] = [dict(row) for row in historical]
            result["coverage"] = coverage
            result["latest_run"] = dict(latest) if latest else None
            return result
