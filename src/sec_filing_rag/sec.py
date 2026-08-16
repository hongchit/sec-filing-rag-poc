from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from .domain import FilingCandidate, latest_original_10k

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_ROOT = "https://data.sec.gov/submissions"
ARCHIVES_ROOT = "https://www.sec.gov/Archives/edgar/data"


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
        self.client = httpx.Client(headers={"User-Agent": identity, "Accept-Encoding": "gzip, deflate"}, timeout=timeout)

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
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in {429, 500, 502, 503, 504}:
                    raise
                if attempt < self.retries:
                    time.sleep(min(2**attempt, 4))
        assert error is not None
        raise error

    def resolve(self, ticker: str) -> tuple[str, str, Fetched]:
        fetched = self.fetch(TICKERS_URL)
        payload: dict[str, dict[str, Any]] = httpx.Response(200, content=fetched.body).json()
        for company in payload.values():
            if str(company["ticker"]).upper() == ticker:
                return f"{int(company['cik_str']):010d}", str(company["title"]), fetched
        raise ValueError("configured ticker is absent from SEC metadata")

    def latest_filing(self, cik: str) -> tuple[FilingCandidate, Fetched, dict[str, Any]]:
        fetched = self.fetch(f"{SUBMISSIONS_ROOT}/CIK{cik}.json")
        payload: dict[str, Any] = httpx.Response(200, content=fetched.body).json()
        return latest_original_10k(payload["filings"]["recent"]), fetched, payload

    def document(self, cik: str, filing: FilingCandidate) -> Fetched:
        accession = filing.accession.replace("-", "")
        return self.fetch(f"{ARCHIVES_ROOT}/{int(cik)}/{accession}/{filing.primary_document}")
