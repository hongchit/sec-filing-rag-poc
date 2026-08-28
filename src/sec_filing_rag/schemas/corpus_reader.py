from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

CorpusItem = Literal["1", "1A", "3", "7", "7A", "8"]


class CorpusParagraph(BaseModel):
    index: int = Field(ge=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str
    is_furniture: bool = False


class HighlightRange(BaseModel):
    paragraph_index: int = Field(ge=1)
    start: int = Field(ge=0, description="Paragraph-local, inclusive character offset")
    end: int = Field(ge=0, description="Paragraph-local, end-exclusive character offset")


class CorpusChunkHighlight(BaseModel):
    chunk_id: str
    citation_handle: str
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    paragraph_start: int = Field(ge=1)
    paragraph_end: int = Field(ge=1)
    ranges: list[HighlightRange]


class CorpusItemSummary(BaseModel):
    item: CorpusItem
    coverage_status: str
    safe_error: str | None = None
    paragraph_count: int = Field(ge=0)
    character_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)


class CorpusVersion(BaseModel):
    corpus_version_id: uuid.UUID
    ticker: str
    company_name: str | None = None
    accession: str
    form: str
    filing_date: date
    report_date: date
    source_url: str
    ready_at: datetime
    is_active: bool
    active_corpus_version_id: uuid.UUID | None = None
    items: list[CorpusItemSummary]


class CorpusItemDocument(BaseModel):
    corpus_version_id: uuid.UUID
    ticker: str
    item: CorpusItem
    coverage_status: str
    safe_error: str | None = None
    source_url: str
    paragraphs: list[CorpusParagraph]
    highlight: CorpusChunkHighlight | None = None


class CorpusChunkLocation(BaseModel):
    chunk_id: str
    corpus_version_id: uuid.UUID
    ticker: str
    item: CorpusItem
    paragraph_index: int = Field(ge=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    citation_handle: str
