from __future__ import annotations

import re
import uuid
from typing import Any

from ..domain.filings import REQUIRED_ITEMS
from .database import Database

_FURNITURE = re.compile(r"(?:^|\s)\|\s*(?:19|20)\d{2}\s+Form\s+10-K\s*\|\s*\d+\s*$", re.I)


def paragraphs(text: str | None) -> list[dict[str, Any]]:
    """Return every non-empty source line with faithful section-relative offsets."""
    if not text:
        return []
    result: list[dict[str, Any]] = []
    offset = 0
    for source_line in text.splitlines(keepends=True):
        # Count the line terminator in the running offset, but exclude it from the
        # paragraph text/span. Blank lines therefore create real gaps between spans.
        line = source_line.rstrip("\r\n")
        if line:
            result.append(
                {
                    "index": len(result) + 1,
                    "start": offset,
                    "end": offset + len(line),
                    "text": line,
                    "is_furniture": bool(_FURNITURE.search(line)),
                }
            )
        offset += len(source_line)
    # splitlines() has no entry for a trailing empty string and handles the final line here.
    if offset < len(text):
        line = text[offset:]
        if line:
            result.append(
                {
                    "index": len(result) + 1,
                    "start": offset,
                    "end": len(text),
                    "text": line,
                    "is_furniture": bool(_FURNITURE.search(line)),
                }
            )
    return result


def highlight_for(
    chunk: dict[str, Any], section_start: int, derived: list[dict[str, Any]]
) -> dict[str, Any] | None:
    # Chunk offsets use the normalized filing as their origin; paragraph offsets use
    # the section. Both persisted values come from the same normalization pass.
    start = int(chunk["source_start"]) - section_start
    end = int(chunk["source_end"]) - section_start
    if start < 0 or end <= start:
        return None
    ranges = []
    for paragraph in derived:
        # Half-open interval intersection avoids marking the next paragraph when a
        # chunk ends exactly on its first character.
        left, right = max(start, paragraph["start"]), min(end, paragraph["end"])
        if left < right:
            ranges.append(
                {
                    "paragraph_index": paragraph["index"],
                    "start": left - paragraph["start"],
                    "end": right - paragraph["start"],
                }
            )
    if not ranges:
        return None
    return {
        "chunk_id": str(chunk["id"]),
        "citation_handle": str(chunk["citation_handle"]),
        "char_start": start,
        "char_end": end,
        "paragraph_start": ranges[0]["paragraph_index"],
        "paragraph_end": ranges[-1]["paragraph_index"],
        "ranges": ranges,
    }


class CorpusReaderRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def version(self, corpus_version_id: uuid.UUID) -> dict[str, Any] | None:
        with self.database.transaction() as connection:
            # Do not filter on company.enabled here. Configuration controls discovery,
            # while a pinned UUID must keep a ready historical citation readable.
            header = connection.execute(
                "SELECT cv.id AS corpus_version_id,cv.ready_at,f.accession,f.form,f.filing_date,"
                "f.report_date,f.source_url,c.ticker,c.name AS company_name,"
                "EXISTS(SELECT 1 FROM public.corpus_activation ca WHERE ca.corpus_version_id=cv.id "
                "AND ca.is_default) AS is_active,(SELECT ca.corpus_version_id FROM public.corpus_activation ca "
                "WHERE ca.company_id=c.id AND ca.is_default) AS active_corpus_version_id "
                "FROM silver.corpus_version cv JOIN silver.filing f ON f.id=cv.filing_id "
                "JOIN public.company c ON c.id=f.company_id WHERE cv.id=%s AND cv.status='ready'",
                (corpus_version_id,),
            ).fetchone()
            if header is None:
                return None
            rows = connection.execute(
                "SELECT s.item,s.coverage_status::text AS coverage_status,s.safe_error,s.text_content,"
                "count(ch.id)::integer AS chunk_count FROM silver.section s LEFT JOIN silver.chunk ch "
                "ON ch.section_id=s.id WHERE s.corpus_version_id=%s "
                "GROUP BY s.id ORDER BY CASE s.item WHEN '1' THEN 1 WHEN '1A' THEN 2 WHEN '3' THEN 3 "
                "WHEN '7' THEN 4 WHEN '7A' THEN 5 WHEN '8' THEN 6 END",
                (corpus_version_id,),
            ).fetchall()
        by_item = {row["item"]: row for row in rows}
        if any(item not in by_item for item in REQUIRED_ITEMS):
            return None
        result = dict(header)
        result["items"] = [
            {
                "item": item,
                "coverage_status": by_item[item]["coverage_status"],
                "safe_error": by_item[item]["safe_error"],
                "paragraph_count": len(paragraphs(by_item[item]["text_content"])),
                "character_count": len(by_item[item]["text_content"] or ""),
                "chunk_count": by_item[item]["chunk_count"],
            }
            for item in REQUIRED_ITEMS
        ]
        return result

    def item(
        self, corpus_version_id: uuid.UUID, item: str, chunk_id: str | None = None
    ) -> dict[str, Any] | None:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT s.id,s.item,s.coverage_status::text AS coverage_status,s.safe_error,"
                "s.text_content,s.source_start,f.source_url,c.ticker FROM silver.section s "
                "JOIN silver.corpus_version cv ON cv.id=s.corpus_version_id "
                "JOIN silver.filing f ON f.id=cv.filing_id JOIN public.company c ON c.id=f.company_id "
                "WHERE s.corpus_version_id=%s AND s.item=%s AND cv.status='ready'",
                (corpus_version_id, item),
            ).fetchone()
            if row is None:
                return None
            chunk = None
            if chunk_id is not None:
                # These redundant predicates are intentional validation: a valid chunk
                # hash from another Item/corpus must not be highlighted in this document.
                chunk = connection.execute(
                    "SELECT id,section_id,corpus_version_id,source_start,source_end,citation_handle "
                    "FROM silver.chunk WHERE id=%s AND section_id=%s AND corpus_version_id=%s",
                    (chunk_id, row["id"], corpus_version_id),
                ).fetchone()
                if chunk is None:
                    return None
        derived = paragraphs(row["text_content"])
        highlight = (
            highlight_for(dict(chunk), int(row["source_start"]), derived)
            if chunk is not None and row["source_start"] is not None
            else None
        )
        if chunk is not None and highlight is None:
            return None
        return {
            "corpus_version_id": corpus_version_id,
            "ticker": row["ticker"],
            "item": row["item"],
            "coverage_status": row["coverage_status"],
            "safe_error": row["safe_error"],
            "source_url": row["source_url"],
            "paragraphs": derived,
            "highlight": highlight,
        }

    def location(self, chunk_id: str) -> dict[str, Any] | None:
        with self.database.transaction() as connection:
            # Silver owns source coordinates. Gold is a replaceable search projection
            # and must not become the authority for reader canonicalization.
            row = connection.execute(
                "SELECT ch.id,ch.corpus_version_id,ch.source_start,ch.source_end,ch.citation_handle,"
                "s.item,s.text_content,s.source_start AS section_start,c.ticker FROM silver.chunk ch "
                "JOIN silver.section s ON s.id=ch.section_id AND s.corpus_version_id=ch.corpus_version_id "
                "JOIN silver.corpus_version cv ON cv.id=ch.corpus_version_id AND cv.status='ready' "
                "JOIN silver.filing f ON f.id=cv.filing_id AND f.id=s.filing_id "
                "JOIN public.company c ON c.id=f.company_id WHERE ch.id=%s",
                (chunk_id,),
            ).fetchone()
        if row is None or row["section_start"] is None:
            return None
        derived = paragraphs(row["text_content"])
        highlight = highlight_for(dict(row), int(row["section_start"]), derived)
        if highlight is None:
            return None
        return {
            "chunk_id": str(row["id"]),
            "corpus_version_id": row["corpus_version_id"],
            "ticker": row["ticker"],
            "item": row["item"],
            "paragraph_index": highlight["paragraph_start"],
            "char_start": highlight["char_start"],
            "char_end": highlight["char_end"],
            "citation_handle": row["citation_handle"],
        }
