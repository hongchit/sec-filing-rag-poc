from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from bs4 import BeautifulSoup, Comment, Tag

Coverage = Literal["present", "legitimately_absent", "failed", "not_assessed"]
REQUIRED_ITEMS = ("1", "1A", "3", "7", "7A", "8")
SUPPORTED_ITEMS = frozenset(REQUIRED_ITEMS)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def compatibility_key(
    *, parser: str, chunker: str, model: str, dimensions: int, index: str, source_checksum: str = ""
) -> str:
    payload = {
        "chunker": chunker,
        "dimensions": dimensions,
        "index": index,
        "model": model,
        "parser": parser,
        "source_checksum": source_checksum,
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def safe_error(error: BaseException | str, secrets: tuple[str, ...] = ()) -> str:
    message = " ".join(str(error).replace("\n", " ").split())
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[REDACTED]")
    message = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", message)
    message = re.sub(
        r"(?i)(?:api[_-]?key|authorization|token|password)\s*[:=]\s*\S+",
        "credential=[REDACTED]",
        message,
    )
    message = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", message)
    fallback = error.__class__.__name__ if isinstance(error, BaseException) else "error"
    return message[:500] or fallback


@dataclass(frozen=True)
class FilingCandidate:
    accession: str
    primary_document: str
    filing_date: date
    report_date: date | None

    @property
    def fiscal_year(self) -> int | None:
        """The SEC report date is the sole source of fiscal-year identity."""
        return self.report_date.year if self.report_date is not None else None


@dataclass(frozen=True)
class AnalysisPeriod:
    granularity: Literal["year"]
    value: int

    @classmethod
    def year(cls, value: str | int) -> AnalysisPeriod:
        raw = str(value)
        if not re.fullmatch(r"[0-9]{4}", raw):
            raise ValueError("period value must be a four-digit year")
        return cls("year", int(raw))


@dataclass(frozen=True)
class Lookback:
    earliest_year: int
    latest_year: int

    def contains(self, year: int) -> bool:
        return self.earliest_year <= year <= self.latest_year


@dataclass(frozen=True)
class FilingSelection:
    requested: AnalysisPeriod
    lookback: Lookback
    exact: FilingCandidate | None
    earlier: FilingCandidate | None
    later: FilingCandidate | None

    @property
    def neighbors(self) -> tuple[FilingCandidate, ...]:
        return tuple(candidate for candidate in (self.earlier, self.later) if candidate is not None)


def lookback_for(candidates: list[FilingCandidate], years: int) -> Lookback:
    if years < 1:
        raise ValueError("lookback years must be positive")
    fiscal_years = [candidate.fiscal_year for candidate in candidates if candidate.fiscal_year is not None]
    if not fiscal_years:
        raise ValueError("no original 10-K filing with a report date found")
    latest = max(fiscal_years)
    return Lookback(latest - years + 1, latest)


def select_fiscal_year(
    candidates: list[FilingCandidate], requested: AnalysisPeriod, years: int
) -> FilingSelection:
    """Select exact/adjacent fiscal years deterministically from original 10-Ks."""
    bounds = lookback_for(candidates, years)
    if not bounds.contains(requested.value):
        raise ValueError("requested year is outside the configured lookback")
    eligible = [
        candidate
        for candidate in candidates
        if candidate.fiscal_year is not None and bounds.contains(candidate.fiscal_year)
    ]
    per_year: dict[int, FilingCandidate] = {}
    for candidate in eligible:
        fiscal_year = candidate.fiscal_year
        assert fiscal_year is not None
        current = per_year.get(fiscal_year)
        if current is None or (candidate.filing_date, candidate.accession) > (
            current.filing_date,
            current.accession,
        ):
            per_year[fiscal_year] = candidate
    exact = per_year.get(requested.value)
    earlier_years = [year for year in per_year if year < requested.value]
    later_years = [year for year in per_year if year > requested.value]
    return FilingSelection(
        requested,
        bounds,
        exact,
        per_year[max(earlier_years)] if earlier_years else None,
        per_year[min(later_years)] if later_years else None,
    )


def confirmed_candidate(selection: FilingSelection, accession: str | None) -> FilingCandidate:
    if selection.exact is not None:
        if accession is not None and accession != selection.exact.accession:
            raise ValueError("exact-year preparation does not accept a different accession")
        return selection.exact
    if accession is None:
        raise ValueError("missing-year preparation requires neighbor confirmation")
    for candidate in selection.neighbors:
        if candidate.accession == accession:
            return candidate
    raise ValueError("confirmed accession is not a current discovery neighbor")


def should_promote_default(*, historical: bool, candidate_complete: bool) -> bool:
    return candidate_complete and not historical


def latest_original_10k(recent: dict[str, list[Any]]) -> FilingCandidate:
    required = ("form", "accessionNumber", "primaryDocument", "filingDate")
    if any(key not in recent for key in required):
        raise ValueError("SEC submissions response lacks required filing columns")
    candidates: list[FilingCandidate] = []
    for index, form in enumerate(recent["form"]):
        if form != "10-K":
            continue
        report_raw = recent.get("reportDate", [None] * len(recent["form"]))[index]
        candidates.append(
            FilingCandidate(
                str(recent["accessionNumber"][index]),
                str(recent["primaryDocument"][index]),
                date.fromisoformat(str(recent["filingDate"][index])),
                date.fromisoformat(str(report_raw)) if report_raw else None,
            )
        )
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


ITEM_TITLE_WORDS = {
    "1": ("business",),
    "1A": ("risk", "factors"),
    "3": ("legal", "proceedings"),
    "7": ("managements", "discussion", "and", "analysis"),
    "7A": ("quantitative", "and", "qualitative", "disclosures", "about", "market", "risk"),
    "8": ("financial", "statements", "and", "supplementary", "data"),
}
_ORDERED_BOUNDARIES = (
    "1",
    "1A",
    "1B",
    "1C",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "7A",
    "8",
    "9",
    "9A",
    "9B",
    "9C",
    "10",
    "11",
    "12",
    "13",
    "14",
    "15",
    "16",
)
_HEADING_SPACE = r"(?:[ \t]+|\n[ \t]*)"
_HEADING_PREFIX = (
    r"(?im)^[ \t]*(?:part" + _HEADING_SPACE + r"[ivx]+[ \t]*[-–—:]?[ \t]*)?item" + _HEADING_SPACE
)
_GENERIC_HEADING = re.compile(
    _HEADING_PREFIX + r"(?P<item>1[0-6]|[1-9])(?P<suffix>[A-C]?)(?:[ \t]*[.\-–—:])?(?:[ \t]+|[ \t]*$)"
)
_PART_HEADING = re.compile(r"(?im)^[ \t]*part\s+[ivx]+\b")
_ABSENCE = re.compile(r"(?i)\b(?:not\s+applicable|none|no\s+(?:material\s+)?(?:legal\s+)?proceedings)\b")
_MIN_BODY = {"1": 120, "1A": 120, "3": 40, "7": 120, "7A": 120, "8": 120}


def sanitize_filing_html(body: bytes, *, max_chars: int) -> str:
    """Return inert narrative text; raw bytes remain a bronze-layer concern only."""
    soup = BeautifulSoup(body, "html.parser")
    for tag in soup.find_all(("script", "style", "noscript", "template", "svg", "iframe", "object", "embed")):
        tag.decompose()
    for tag in list(soup.find_all(True)):
        if not isinstance(tag, Tag) or tag.attrs is None:
            continue
        style = str(tag.get("style", "")).lower().replace(" ", "")
        hidden = tag.has_attr("hidden") or str(tag.get("aria-hidden", "")).lower() == "true"
        if hidden or "display:none" in style or "visibility:hidden" in style:
            tag.decompose()
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    narrative = unicodedata.normalize("NFKC", soup.get_text("\n", strip=True))
    narrative = "".join(
        character
        for character in narrative
        if character in {"\n", "\t"} or unicodedata.category(character) not in {"Cc", "Cf"}
    )
    narrative = re.sub(r"[ \t]+", " ", narrative)
    narrative = re.sub(r"\n[ \t]*\n+", "\n", narrative).strip()
    if len(narrative) > max_chars:
        raise ValueError("normalized filing narrative exceeds configured size limit")
    return narrative


def normalize_narrative(text: str) -> str:
    return re.sub(r"\r\n?", "\n", text).replace("\u00a0", " ")


def _heading_pattern(item: str) -> re.Pattern[str]:
    words: list[str] = []
    for word in ITEM_TITLE_WORDS[item]:
        if word == "managements":
            prefix = r"[ \t\n]*".join(re.escape(character) for character in "management")
            words.append(prefix + r"[ \t\n]*(?:['’][ \t\n]*)?s")
        else:
            words.append(r"[ \t\n]*".join(re.escape(character) for character in word))
    title = _HEADING_SPACE.join(words)
    return re.compile(
        _HEADING_PREFIX + re.escape(item) + r"(?:[ \t]*[.\-–—:])?[ \t]*(?:\n[ \t]*){0,3}" + title + r"\b"
    )


def _next_boundary(text: str, start: int, item: str) -> re.Match[str] | None:
    current = _ORDERED_BOUNDARIES.index(item)
    generic = next(
        (
            match
            for match in _GENERIC_HEADING.finditer(text, start)
            if (match.group("item") + match.group("suffix").upper()) in _ORDERED_BOUNDARIES
            and _ORDERED_BOUNDARIES.index(match.group("item") + match.group("suffix").upper()) > current
        ),
        None,
    )
    part = _PART_HEADING.search(text, start)
    if generic is None:
        return part
    if part is None:
        return generic
    return generic if generic.start() < part.start() else part


def extract_item(text: str, item: str, *, normalized: bool = False) -> ExtractedSection:
    if item not in SUPPORTED_ITEMS:
        raise ValueError("unsupported filing item")
    narrative = text if normalized else normalize_narrative(text)
    choices: list[tuple[int, int, str]] = []
    explicit_absence = False
    saw_unbounded = False
    for heading in _heading_pattern(item).finditer(narrative):
        boundary = _next_boundary(narrative, heading.end(), item)
        if boundary is None:
            saw_unbounded = True
            continue
        raw = narrative[heading.start() : boundary.start()]
        body = raw.strip()
        section_body = narrative[heading.end() : boundary.start()].strip()
        if _ABSENCE.search(section_body) and len(section_body) < _MIN_BODY[item]:
            explicit_absence = True
            continue
        if len(body) >= _MIN_BODY[item]:
            leading = len(raw) - len(raw.lstrip())
            choices.append((heading.start() + leading, heading.start() + leading + len(body), body))
    if not choices:
        if explicit_absence:
            return ExtractedSection(
                "legitimately_absent", error=safe_error(f"Item {item} explicitly not applicable")
            )
        reason = (
            f"Item {item} end boundary not found"
            if saw_unbounded
            else f"Item {item} heading or usable content not found"
        )
        return ExtractedSection("failed", error=safe_error(reason))
    choices.sort(key=lambda value: value[1] - value[0], reverse=True)
    if len(choices) > 1 and choices[1][1] - choices[1][0] >= (choices[0][1] - choices[0][0]) * 0.8:
        return ExtractedSection("failed", error=safe_error(f"Item {item} has ambiguous section boundaries"))
    start, end, body = choices[0]
    return ExtractedSection("present", body, start, end)


def extract_sections(text: str) -> dict[str, ExtractedSection]:
    narrative = normalize_narrative(text)
    results: dict[str, ExtractedSection] = {}
    for item in REQUIRED_ITEMS:
        try:
            results[item] = extract_item(narrative, item, normalized=True)
        except Exception as exc:
            results[item] = ExtractedSection("not_assessed", error=safe_error(exc))
    return results


def extract_item_1a(text: str) -> ExtractedSection:
    return extract_item(text, "1A")


@dataclass(frozen=True)
class Chunk:
    id: str
    ordinal: int
    text: str
    start: int
    end: int
    citation: str
    sha256: str


def make_chunks(
    text: str,
    *,
    accession: str,
    item: str,
    version: str,
    size: int,
    overlap: int,
    base_offset: int = 0,
) -> list[Chunk]:
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
        raw = text[start:end]
        left = len(raw) - len(raw.lstrip())
        right = len(raw.rstrip())
        content = raw[left:right]
        if content:
            ordinal = len(chunks)
            citation = f"{accession}:item-{item.lower()}:{ordinal:04d}"
            digest = sha256_bytes(content.encode())
            identity = sha256_bytes(f"{accession}|{item}|{version}|{ordinal}|{digest}".encode())
            chunks.append(
                Chunk(
                    identity,
                    ordinal,
                    content,
                    base_offset + start + left,
                    base_offset + start + right,
                    citation,
                    digest,
                )
            )
        if end == len(text):
            break
        start = end - overlap
    return chunks
