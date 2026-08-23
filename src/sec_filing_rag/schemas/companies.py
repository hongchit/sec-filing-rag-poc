from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel


class CompanySummary(BaseModel):
    ticker: str
    enabled: bool
    cik: int | None = None
    name: str | None = None
    resolution_status: str
    safe_error: str | None = None
    accession: str | None = None
    filing_date: date | None = None
    corpus_status: str | None = None
    ready_at: datetime | None = None
    latest_run_status: str | None = None


class ActiveCorpus(BaseModel):
    corpus_version_id: uuid.UUID
    ready_at: datetime
    embedding_model: str
    embedding_dimensions: int
    accession: str
    filing_date: date
    report_date: date
    source_url: str
    embedding_usage_status: str | None = None


class CorpusCoverage(BaseModel):
    item: str
    status: str
    safe_error: str | None = None
    chunk_count: int
    search_document_count: int


class LatestRun(BaseModel):
    run_id: uuid.UUID
    status: str
    stage: str
    section_count: int | None = None
    chunk_count: int | None = None
    safe_error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class HistoricalCorpus(BaseModel):
    corpus_version_id: uuid.UUID
    ready_at: datetime
    accession: str
    report_date: date
    filing_date: date


class CompanyStatus(BaseModel):
    ticker: str
    enabled: bool
    cik: int | None = None
    name: str | None = None
    resolution_status: str | None = None
    safe_error: str | None = None
    active_corpus: ActiveCorpus | None = None
    historical_corpora: list[HistoricalCorpus] = []
    coverage: list[CorpusCoverage]
    latest_run: LatestRun | None = None
