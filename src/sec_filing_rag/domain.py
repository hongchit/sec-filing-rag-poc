from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

Coverage = Literal["present", "legitimately_absent", "failed", "not_assessed"]
SUPPORTED_ITEMS = {"1A"}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def compatibility_key(*, parser: str, chunker: str, model: str, dimensions: int, index: str) -> str:
    payload = {"chunker": chunker, "dimensions": dimensions, "index": index, "model": model, "parser": parser}
    return sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def safe_error(error: BaseException | str, secrets: tuple[str, ...] = ()) -> str:
    message = " ".join(str(error).replace("\n", " ").split())
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[REDACTED]")
    message = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", message)
    fallback = error.__class__.__name__ if isinstance(error, BaseException) else "error"
    return message[:500] or fallback


@dataclass(frozen=True)
class FilingCandidate:
    accession: str
    primary_document: str
    filing_date: date
    report_date: date | None


def latest_original_10k(recent: dict[str, list[Any]]) -> FilingCandidate:
    required = ("form", "accessionNumber", "primaryDocument", "filingDate")
    if any(key not in recent for key in required):
        raise ValueError("SEC submissions response lacks required filing columns")
    candidates: list[FilingCandidate] = []
    for index, form in enumerate(recent["form"]):
        if form != "10-K":
            continue
        report_raw = recent.get("reportDate", [None] * len(recent["form"]))[index]
        candidates.append(FilingCandidate(str(recent["accessionNumber"][index]), str(recent["primaryDocument"][index]), date.fromisoformat(str(recent["filingDate"][index])), date.fromisoformat(str(report_raw)) if report_raw else None))
    if not candidates:
        raise ValueError("no original 10-K filing found")
    return max(candidates, key=lambda candidate: candidate.filing_date)


@dataclass(frozen=True)
class ExtractedSection:
    status: Coverage
    text: str | None = None
    start: int | None = None
    end: int | None = None
    error: str | None = None


ITEM_1A = re.compile(r"(?im)^\s*(?:item\s+)?1a[.\s:-]+risk\s+factors\b")
NEXT_ITEM = re.compile(r"(?im)^\s*(?:item\s+)?1b[.\s:-]+|^\s*(?:item\s+)?2[.\s:-]+properties\b")


def extract_item_1a(text: str) -> ExtractedSection:
    normalized = re.sub(r"\r\n?", "\n", text)
    headings = list(ITEM_1A.finditer(normalized))
    if not headings:
        return ExtractedSection("legitimately_absent")
    choices = []
    for heading in headings:
        boundary = NEXT_ITEM.search(normalized, heading.end())
        if boundary:
            choices.append((heading.start(), boundary.start()))
    if not choices:
        return ExtractedSection("failed", error="Item 1A end boundary not found")
    start, end = max(choices, key=lambda pair: pair[1] - pair[0])
    section = normalized[start:end].strip()
    if len(section) < 200:
        return ExtractedSection("failed", error="Item 1A content below conservative minimum")
    return ExtractedSection("present", section, start, end)


@dataclass(frozen=True)
class Chunk:
    id: str
    ordinal: int
    text: str
    start: int
    end: int
    citation: str
    sha256: str


def make_chunks(text: str, *, accession: str, item: str, version: str, size: int, overlap: int) -> list[Chunk]:
    if overlap >= size:
        raise ValueError("chunk overlap must be smaller than chunk size")
    chunks: list[Chunk] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            split = text.rfind("\n", start + size // 2, end)
            if split > start:
                end = split
        content = text[start:end].strip()
        if content:
            ordinal = len(chunks)
            citation = f"{accession}:item-{item.lower()}:{ordinal:04d}"
            digest = sha256_bytes(content.encode())
            identity = sha256_bytes(f"{accession}|{item}|{version}|{ordinal}|{digest}".encode())
            chunks.append(Chunk(identity, ordinal, content, start, end, citation, digest))
        if end == len(text):
            break
        start = end - overlap
    return chunks
