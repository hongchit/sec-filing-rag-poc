from __future__ import annotations

import importlib
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from ..core.errors import UpstreamServiceError
from ..domain.filings import FilingCandidate, sha256_bytes

EDGARTOOLS_VERSION = "5.41.0"
_ACCESSION = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")


@dataclass(frozen=True)
class EdgarCompanySnapshot:
    requested_ticker: str
    cik: str
    name: str
    tickers: tuple[str, ...]
    exchanges: tuple[str, ...]
    sic: str | None = None
    industry: str | None = None
    fiscal_year_end: str | None = None
    filer_type: str | None = None
    is_company: bool | None = None
    edgartools_version: str = EDGARTOOLS_VERSION


@dataclass(frozen=True)
class EdgarFilingMetadata:
    accession: str
    form: str
    filing_date: date
    report_date: date
    acceptance_datetime: datetime | None
    act: str | None
    file_number: str | None
    size: int | None
    is_xbrl: bool | None
    is_inline_xbrl: bool | None
    primary_document: str
    primary_document_description: str | None
    homepage_url: str
    filing_url: str
    text_url: str


@dataclass(frozen=True)
class EdgarFilingDocument:
    name: str
    document_type: str
    sequence: str | None
    description: str | None
    source_url: str
    content: bytes
    media_type: str = "text/html"
    content_encoding: str = "utf-8"

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.content)


@dataclass(frozen=True)
class AcquiredFiling:
    company: EdgarCompanySnapshot
    filing: EdgarFilingMetadata
    document: EdgarFilingDocument


class EdgarFacade(Protocol):
    def ticker_rows(self) -> Iterable[Mapping[str, Any]]: ...
    def company(self, cik: int) -> Any: ...
    def filings(self, company: Any, *, full: bool) -> Iterable[Any]: ...


class _SdkFacade:
    """The sole boundary at which EdgarTools SDK objects are exposed."""

    def __init__(self) -> None:
        from edgar import Company, get_company_tickers  # type: ignore[import-untyped]

        self._company = Company
        self._tickers = get_company_tickers

    def ticker_rows(self) -> Iterable[Mapping[str, Any]]:
        value = self._tickers()
        if hasattr(value, "to_dict"):
            rows: list[dict[str, Any]] = value.to_dict(orient="records")
            return rows
        if isinstance(value, Mapping):
            return (row for row in value.values() if isinstance(row, Mapping))
        return list(value)

    def company(self, cik: int) -> Any:
        return self._company(cik)

    def filings(self, company: Any, *, full: bool) -> Iterable[Any]:
        filings = company.get_filings(form="10-K", amendments=False, trigger_full_load=full)
        # to_pandas() yields primitive metadata without fetching every filing document.
        rows = filings.to_pandas().to_dict(orient="records")
        accessions = {_text(row.get("accession_number") or row.get("accession")) for row in rows}
        return (
            filing
            for filing in filings
            if _text(getattr(filing, "accession_number", None)) in accessions
        )


def configure_edgartools(
    identity: str, rate_limit: int = 6, access_mode: str = "CAUTION"
) -> EdgarFacade:
    """Set provider controls before the first SDK import, when EdgarTools reads its environment."""
    os.environ["EDGAR_IDENTITY"] = identity
    os.environ["EDGAR_RATE_LIMIT_PER_SEC"] = str(rate_limit)
    os.environ["EDGAR_ACCESS_MODE"] = access_mode
    from edgar import set_identity

    set_identity(identity)
    httpclient = importlib.import_module("edgar.httpclient")
    if httpclient.get_edgar_rate_limit_per_sec() != rate_limit:
        raise RuntimeError("EdgarTools rate limiter configuration was not applied")
    core = importlib.import_module("edgar.core")
    if access_mode != "CAUTION" or core.edgar_mode is not core.CAUTION:
        raise RuntimeError("EdgarTools CAUTION access mode was not applied")
    return _SdkFacade()


class EdgarGateway:
    def __init__(self, *, facade: EdgarFacade) -> None:
        self._facade = facade
        # Operation-local caches prevent duplicate provider resolution and discovery work.
        self._companies: dict[str, tuple[EdgarCompanySnapshot, Any]] = {}
        self._filings: dict[
            tuple[str, bool, str | None], list[tuple[EdgarFilingMetadata, Any]]
        ] = {}
        self._candidates: dict[str, list[FilingCandidate]] = {}

    @staticmethod
    def _upstream(message: str, exc: BaseException | None = None) -> UpstreamServiceError:
        error = UpstreamServiceError(
            message,
            public_detail="SEC filing discovery is temporarily unavailable",
            code="sec_provider_failure",
        )
        if exc is not None:
            error.__cause__ = exc
        return error

    def resolve(self, ticker: str) -> EdgarCompanySnapshot:
        normalized = ticker.strip().upper()
        matches: dict[str, Mapping[str, Any]] = {}
        try:
            for row in self._facade.ticker_rows():
                if _text(row.get("ticker")).upper() == normalized:
                    value = row.get("cik") if "cik" in row else row.get("cik_str")
                    matches[_cik(value)] = row
        except Exception as exc:
            raise self._upstream("EdgarTools ticker resolution failed", exc) from exc
        if not matches:
            raise self._upstream("ticker is absent from EdgarTools metadata")
        if len(matches) != 1:
            raise self._upstream("ticker maps to multiple distinct CIKs")
        cik, row = next(iter(matches.items()))
        if cik in self._companies:
            return self._companies[cik][0]
        try:
            company = self._facade.company(int(cik))
            snapshot = EdgarCompanySnapshot(
                normalized,
                cik,
                _required(
                    getattr(company, "name", None) or row.get("company") or row.get("title"),
                    "company name",
                ),
                _strings(getattr(company, "tickers", None) or [normalized]),
                _strings(getattr(company, "exchanges", None)),
                _optional(getattr(company, "sic", None)),
                _optional(getattr(company, "industry", None)),
                _optional(getattr(company, "fiscal_year_end", None)),
                _optional(
                    getattr(company, "filer_category", None) or getattr(company, "filer_type", None)
                ),
                _boolean(getattr(company, "is_company", None)),
            )
        except Exception as exc:
            raise self._upstream("EdgarTools company lookup failed", exc) from exc
        self._companies[cik] = (snapshot, company)
        return snapshot

    def discover_candidates(self, ticker: str) -> tuple[str, str, list[FilingCandidate]]:
        company = self.resolve(ticker)
        if company.cik in self._candidates:
            return company.cik, company.name, self._candidates[company.cik]
        try:
            values = self._facade.filings(self._companies[company.cik][1], full=True)
            candidates = [
                self._candidate(value)
                for value in values
                if _text(getattr(value, "form", None)) == "10-K"
            ]
        except Exception as exc:
            if isinstance(exc, UpstreamServiceError):
                raise
            raise self._upstream("EdgarTools filing discovery failed", exc) from exc
        deduplicated: dict[str, FilingCandidate] = {}
        for candidate in candidates:
            current = deduplicated.get(candidate.accession)
            if current is None or candidate.filing_date > current.filing_date:
                deduplicated[candidate.accession] = candidate
        filings = sorted(
            deduplicated.values(),
            key=lambda candidate: (
                candidate.report_date or date.min,
                candidate.filing_date,
                candidate.accession,
            ),
            reverse=True,
        )
        if not filings:
            raise self._upstream("company has no original 10-K filing")
        self._candidates[company.cik] = filings
        return company.cik, company.name, filings

    def acquire(
        self, ticker: str, *, accession: str | None = None, max_bytes: int
    ) -> AcquiredFiling:
        company = self.resolve(ticker)
        pairs = self._load(company, full=accession is not None, accession=accession)
        if accession is None:
            if not pairs:
                raise self._upstream("company has no original 10-K filing")
            metadata, sdk = max(pairs, key=lambda pair: (pair[0].filing_date, pair[0].accession))
        else:
            if not _ACCESSION.fullmatch(accession):
                raise ValueError("requested accession is malformed")
            selected = [pair for pair in pairs if pair[0].accession == accession]
            if not selected:
                raise ValueError("requested accession is not an original 10-K")
            metadata, sdk = selected[0]
        try:
            html = sdk.html()
        except Exception as exc:
            raise self._upstream("EdgarTools filing HTML retrieval failed", exc) from exc
        if not isinstance(html, str) or not html.strip():
            raise self._upstream("EdgarTools returned missing filing HTML")
        content = html.encode("utf-8")
        if len(content) > max_bytes:
            raise self._upstream("filing document exceeds configured size limit")
        lowered = metadata.primary_document.lower()
        html_start = html.lstrip().lower()
        # Inline-XBRL primary documents may validly begin with an XML declaration.
        if not lowered.endswith((".htm", ".html")) or not html_start.startswith(
            ("<!doctype html", "<html", "<xhtml", "<?xml")
        ):
            raise self._upstream("EdgarTools primary document is not HTML")
        return AcquiredFiling(
            company,
            metadata,
            EdgarFilingDocument(
                metadata.primary_document,
                metadata.form,
                _optional(
                    getattr(getattr(sdk, "document", None), "sequence_number", None)
                    or getattr(sdk, "sequence", None)
                ),
                metadata.primary_document_description,
                metadata.filing_url,
                content,
            ),
        )

    def _load(
        self, company: EdgarCompanySnapshot, *, full: bool, accession: str | None
    ) -> list[tuple[EdgarFilingMetadata, Any]]:
        key = (company.cik, full, accession)
        if key in self._filings:
            return self._filings[key]
        try:
            values = self._facade.filings(self._companies[company.cik][1], full=full)
            # Filter a requested accession before enrichment so malformed unrelated history
            # cannot prevent acquisition of the explicitly selected filing.
            normalized = [
                (self._metadata(value), value)
                for value in values
                if _text(getattr(value, "form", None)) == "10-K"
                and (
                    accession is None
                    or _text(getattr(value, "accession_number", None)) == accession
                )
            ]
        except Exception as exc:
            raise self._upstream("EdgarTools filing discovery failed", exc) from exc
        deduplicated: dict[str, tuple[EdgarFilingMetadata, Any]] = {}
        for pair in normalized:
            current = deduplicated.get(pair[0].accession)
            if current is None or pair[0].filing_date > current[0].filing_date:
                deduplicated[pair[0].accession] = pair
        result = sorted(
            deduplicated.values(),
            key=lambda pair: (pair[0].report_date, pair[0].filing_date, pair[0].accession),
            reverse=True,
        )
        self._filings[key] = result
        return result

    @staticmethod
    def _candidate(filing: Any) -> FilingCandidate:
        accession = _required(
            getattr(filing, "accession_number", None) or getattr(filing, "accession", None),
            "accession",
        )
        if not _ACCESSION.fullmatch(accession):
            raise ValueError("EdgarTools returned malformed accession")
        return FilingCandidate(
            accession,
            _date(getattr(filing, "filing_date", None), "filing date"),
            _date(getattr(filing, "period_of_report", None), "report date"),
        )

    @staticmethod
    def _metadata(filing: Any) -> EdgarFilingMetadata:
        accession = _required(
            getattr(filing, "accession_number", None) or getattr(filing, "accession", None),
            "accession",
        )
        if not _ACCESSION.fullmatch(accession):
            raise ValueError("EdgarTools returned malformed accession")
        # Filing.document is an EdgarTools attachment object, not merely a filename.
        attachment = getattr(filing, "document", None)
        document_name = getattr(attachment, "document", attachment)
        document_description = getattr(attachment, "description", None) or getattr(
            filing, "primary_document_description", None
        )
        return EdgarFilingMetadata(
            accession,
            _required(getattr(filing, "form", None), "form"),
            _date(getattr(filing, "filing_date", None), "filing date"),
            _date(getattr(filing, "period_of_report", None), "report date"),
            _datetime(getattr(filing, "acceptance_datetime", None)),
            _optional(getattr(filing, "act", None)),
            _optional(getattr(filing, "file_number", None)),
            _integer(getattr(filing, "size", None)),
            _boolean(getattr(filing, "is_xbrl", None)),
            _boolean(getattr(filing, "is_inline_xbrl", None)),
            _required(document_name, "primary document"),
            _optional(document_description),
            _required(getattr(filing, "homepage_url", None), "filing homepage URL"),
            _required(getattr(filing, "filing_url", None), "primary filing URL"),
            _required(getattr(filing, "text_url", None), "full-text submission URL"),
        )


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _required(value: Any, name: str) -> str:
    result = _text(value)
    if not result:
        raise ValueError(f"EdgarTools returned missing {name}")
    return result


def _optional(value: Any) -> str | None:
    return _text(value) or None


def _strings(value: Any) -> tuple[str, ...]:
    values = value.split(",") if isinstance(value, str) else value or ()
    return tuple(dict.fromkeys(_text(item) for item in values if _text(item)))


def _cik(value: Any) -> str:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("EdgarTools returned malformed CIK") from exc
    if not 0 < number <= 9_999_999_999:
        raise ValueError("EdgarTools returned malformed CIK")
    return f"{number:010d}"


def _date(value: Any, name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(_required(value, name)[:10])
    except ValueError as exc:
        raise ValueError(f"EdgarTools returned malformed {name}") from exc


def _datetime(value: Any) -> datetime | None:
    if value is None or not _text(value):
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("EdgarTools returned malformed acceptance timestamp") from exc


def _integer(value: Any) -> int | None:
    if value is None or not _text(value):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("EdgarTools returned malformed filing size") from exc
    if result < 0:
        raise ValueError("EdgarTools returned malformed filing size")
    return result


def _boolean(value: Any) -> bool | None:
    if value is None or not _text(value):
        return None
    if isinstance(value, bool):
        return value
    normalized = _text(value).lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError("EdgarTools returned malformed boolean metadata")
