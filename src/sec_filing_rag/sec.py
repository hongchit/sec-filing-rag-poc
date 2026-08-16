from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import quote, urljoin, urlparse
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup, Tag

from .domain import FilingCandidate, latest_original_10k

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_ROOT = "https://data.sec.gov/submissions"
ARCHIVES_ROOT = "https://www.sec.gov/Archives/edgar/data"
BROWSE_ROOT = "https://www.sec.gov/cgi-bin/browse-edgar"


@dataclass(frozen=True)
class Fetched:
    url: str
    body: bytes
    status: int
    headers: dict[str, str]


class SecClient:
    def __init__(self, *, identity: str, timeout: float, retries: int, interval: float) -> None:
        self.interval = interval
        self.retries = retries
        self._last_request = 0.0
        self._filing_cache: dict[str, tuple[FilingCandidate, Fetched, dict[str, Any]]] = {}
        self.client = httpx.Client(
            headers={"User-Agent": identity, "Accept-Encoding": "gzip, deflate"}, timeout=timeout
        )

    def fetch(self, url: str) -> Fetched:
        error: Exception | None = None
        for attempt in range(self.retries + 1):
            wait = self.interval - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            try:
                response = self.client.get(url)
                self._last_request = time.monotonic()
                response.raise_for_status()
                return Fetched(url, response.content, response.status_code, dict(response.headers))
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                error = exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in {
                    429,
                    500,
                    502,
                    503,
                    504,
                }:
                    raise
                if attempt < self.retries:
                    time.sleep(min(2**attempt, 4))
        assert error is not None
        raise error

    def resolve(self, ticker: str) -> tuple[str, str, Fetched]:
        fetched = self.fetch(TICKERS_URL)
        payload: dict[str, dict[str, Any]] = httpx.Response(200, content=fetched.body).json()
        matches = [company for company in payload.values() if str(company["ticker"]).upper() == ticker]
        if matches:
            issuers: list[tuple[FilingCandidate, str, str]] = []
            for company in matches[:20]:
                cik = f"{int(company['cik_str']):010d}"
                try:
                    filing, submission_fetch, submission = self.latest_filing(cik)
                except ValueError as exc:
                    if str(exc) == "no original 10-K filing found":
                        continue
                    raise
                self._filing_cache[cik] = (filing, submission_fetch, submission)
                issuers.append((filing, cik, str(company["title"])))
            if issuers:
                _, cik, name = max(issuers, key=lambda entry: entry[0].filing_date)
                return cik, name, fetched
            return self._resolve_ticker_atom(ticker, fetched)
        raise ValueError("configured ticker is absent from SEC metadata")

    def _resolve_ticker_atom(self, ticker: str, ticker_fetch: Fetched) -> tuple[str, str, Fetched]:
        atom_url = (
            f"{BROWSE_ROOT}?action=getcompany&CIK={quote(ticker, safe='')}&type=10-K&owner=exclude&"
            "output=atom&count=40"
        )
        atom = self.fetch(atom_url)
        if len(atom.body) > 5_000_000:
            raise ValueError("SEC ticker filing index exceeds safe size limit")
        try:
            root = ElementTree.fromstring(atom.body)
        except ElementTree.ParseError as exc:
            raise ValueError("SEC ticker filing index response is invalid") from exc
        company_name = next(
            (
                (element.text or "").strip()
                for element in root.iter()
                if element.tag.rsplit("}", 1)[-1] == "conformed-name" and (element.text or "").strip()
            ),
            ticker,
        )
        candidates: list[tuple[date, str]] = []
        for entry in root.iter():
            if entry.tag.rsplit("}", 1)[-1] != "entry":
                continue
            values = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in entry.iter()}
            if values.get("filing-type") != "10-K":
                continue
            accession = values.get("accession-number", "")
            parsed = urlparse(values.get("filing-href", ""))
            path = re.fullmatch(
                r"/Archives/edgar/data/(?P<cik>[0-9]+)/(?P<directory>[0-9]+)/[^/]+-index\.htm",
                parsed.path,
            )
            if (
                parsed.scheme != "https"
                or parsed.hostname != "www.sec.gov"
                or path is None
                or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession)
                or path.group("directory") != accession.replace("-", "")
            ):
                continue
            try:
                filing_date = date.fromisoformat(values["filing-date"])
            except (KeyError, ValueError):
                continue
            candidates.append((filing_date, f"{int(path.group('cik')):010d}"))
        if not candidates:
            raise ValueError("ticker matches SEC metadata but no matching issuer has an original 10-K")
        _, cik = max(candidates, key=lambda entry: entry[0])
        filing, submission_fetch, submission = self.latest_filing(cik)
        self._filing_cache[cik] = (filing, submission_fetch, submission)
        return cik, company_name, ticker_fetch

    def latest_filing(self, cik: str) -> tuple[FilingCandidate, Fetched, dict[str, Any]]:
        cached = self._filing_cache.get(cik)
        if cached is not None:
            return cached
        fetched = self.fetch(f"{SUBMISSIONS_ROOT}/CIK{cik}.json")
        payload: dict[str, Any] = httpx.Response(200, content=fetched.body).json()
        try:
            result = (latest_original_10k(payload["filings"]["recent"]), fetched, payload)
            self._filing_cache[cik] = result
            return result
        except ValueError as exc:
            if str(exc) != "no original 10-K filing found":
                raise
        historical: list[tuple[FilingCandidate, Fetched, dict[str, Any]]] = []
        for descriptor in payload.get("filings", {}).get("files", []):
            name = str(descriptor.get("name", ""))
            if not re.fullmatch(r"CIK[0-9]{10}-submissions-[0-9]{3}\.json", name):
                continue
            history_fetch = self.fetch(f"{SUBMISSIONS_ROOT}/{name}")
            history_payload: dict[str, Any] = httpx.Response(200, content=history_fetch.body).json()
            try:
                candidate = latest_original_10k(history_payload)
            except ValueError as exc:
                if str(exc) == "no original 10-K filing found":
                    continue
                raise
            historical.append((candidate, history_fetch, history_payload))
        if not historical:
            result = self._latest_atom_filing(cik, fetched, payload)
        else:
            result = max(historical, key=lambda entry: entry[0].filing_date)
        self._filing_cache[cik] = result
        return result

    def _latest_atom_filing(
        self, cik: str, submission_fetch: Fetched, submission: dict[str, Any]
    ) -> tuple[FilingCandidate, Fetched, dict[str, Any]]:
        atom_url = f"{BROWSE_ROOT}?action=getcompany&CIK={cik}&type=10-K&owner=exclude&output=atom&count=40"
        atom = self.fetch(atom_url)
        if len(atom.body) > 5_000_000:
            raise ValueError("SEC filing index response exceeds safe size limit")
        try:
            root = ElementTree.fromstring(atom.body)
        except ElementTree.ParseError as exc:
            raise ValueError("SEC filing index response is invalid") from exc
        entries: list[tuple[date, date | None, str, str]] = []
        for entry in root.iter():
            if entry.tag.rsplit("}", 1)[-1] != "entry":
                continue
            values = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in entry.iter()}
            if values.get("filing-type") != "10-K":
                continue
            accession = values.get("accession-number", "")
            href = values.get("filing-href", "")
            if not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
                continue
            parsed = urlparse(href)
            expected = f"/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
            if (
                parsed.scheme != "https"
                or parsed.hostname != "www.sec.gov"
                or not parsed.path.startswith(expected)
            ):
                continue
            try:
                filing_date = date.fromisoformat(values["filing-date"])
                period_raw = values.get("period", "")
                report_date = (
                    date.fromisoformat(period_raw)
                    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", period_raw)
                    else date.fromisoformat(f"{period_raw[:4]}-{period_raw[4:6]}-{period_raw[6:]}")
                    if re.fullmatch(r"[0-9]{8}", period_raw)
                    else None
                )
            except (KeyError, ValueError):
                continue
            entries.append((filing_date, report_date, accession, href))
        if not entries:
            raise ValueError("no original 10-K filing found")
        filing_date, report_date, accession, index_url = max(entries, key=lambda value: value[0])
        index = self.fetch(index_url)
        if len(index.body) > 5_000_000:
            raise ValueError("SEC filing document index exceeds safe size limit")
        soup = BeautifulSoup(index.body, "html.parser")
        primary_document: str | None = None
        expected_path = f"/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
        for row in soup.find_all("tr"):
            if not isinstance(row, Tag):
                continue
            cells = row.find_all("td")
            if not any(isinstance(cell, Tag) and cell.get_text(" ", strip=True) == "10-K" for cell in cells):
                continue
            anchor = row.find("a", href=True)
            if not isinstance(anchor, Tag):
                continue
            document_url = urljoin(index_url, str(anchor.get("href", "")))
            parsed = urlparse(document_url)
            if (
                parsed.scheme != "https"
                or parsed.hostname != "www.sec.gov"
                or not parsed.path.startswith(expected_path)
            ):
                continue
            name = parsed.path.rsplit("/", 1)[-1]
            if re.fullmatch(r"[A-Za-z0-9._-]+\.(?:htm|html)", name):
                primary_document = name
                break
        if primary_document is None:
            raise ValueError("original 10-K primary document not found in SEC filing index")
        return (
            FilingCandidate(accession, primary_document, filing_date, report_date),
            submission_fetch,
            submission,
        )

    def discover_candidates(self, ticker: str) -> tuple[str, str, list[FilingCandidate]]:
        """Enumerate deduplicated original 10-Ks for read-only fiscal discovery."""
        cik, name, _ = self.resolve(ticker)
        fetched = self.fetch(f"{SUBMISSIONS_ROOT}/CIK{cik}.json")
        payload: dict[str, Any] = httpx.Response(200, content=fetched.body).json()
        candidates = self._candidates_from_columns(payload.get("filings", {}).get("recent", {}))
        for descriptor in payload.get("filings", {}).get("files", []):
            filename = str(descriptor.get("name", ""))
            if not re.fullmatch(r"CIK[0-9]{10}-submissions-[0-9]{3}\.json", filename):
                continue
            historical = self.fetch(f"{SUBMISSIONS_ROOT}/{filename}")
            columns: dict[str, list[Any]] = httpx.Response(200, content=historical.body).json()
            candidates.extend(self._candidates_from_columns(columns))
        if not candidates:
            candidate, _, _ = self._latest_atom_filing(cik, fetched, payload)
            candidates.append(candidate)
        deduplicated: dict[str, FilingCandidate] = {}
        for candidate in candidates:
            current = deduplicated.get(candidate.accession)
            if current is None or (candidate.filing_date, candidate.primary_document) > (
                current.filing_date,
                current.primary_document,
            ):
                deduplicated[candidate.accession] = candidate
        return (
            cik,
            name,
            sorted(
                deduplicated.values(),
                key=lambda candidate: (
                    candidate.report_date or date.min,
                    candidate.filing_date,
                    candidate.accession,
                ),
                reverse=True,
            ),
        )

    @staticmethod
    def _candidates_from_columns(columns: dict[str, list[Any]]) -> list[FilingCandidate]:
        required = ("form", "accessionNumber", "primaryDocument", "filingDate")
        if any(key not in columns for key in required):
            return []
        result: list[FilingCandidate] = []
        for index, form in enumerate(columns["form"]):
            if form != "10-K":
                continue
            try:
                report_values = columns.get("reportDate", [])
                report_raw = report_values[index] if index < len(report_values) else None
                result.append(
                    FilingCandidate(
                        str(columns["accessionNumber"][index]),
                        str(columns["primaryDocument"][index]),
                        date.fromisoformat(str(columns["filingDate"][index])),
                        date.fromisoformat(str(report_raw)) if report_raw else None,
                    )
                )
            except (IndexError, ValueError):
                continue
        return result

    def document(self, cik: str, filing: FilingCandidate) -> Fetched:
        accession = filing.accession.replace("-", "")
        return self.fetch(f"{ARCHIVES_ROOT}/{int(cik)}/{accession}/{filing.primary_document}")
