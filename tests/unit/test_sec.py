from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from sec_filing_rag.core.errors import UpstreamServiceError
from sec_filing_rag.integrations.sec import EdgarGateway


class FakeFacade:
    def __init__(self, rows: list[dict[str, Any]], filings: list[Any] | None = None) -> None:
        self.rows = rows
        self.values = filings or []
        self.company_calls = 0
        self.filing_calls: list[bool] = []
        self.company_value = SimpleNamespace(
            name="Example Corp",
            tickers=["EX"],
            exchanges=["NYSE"],
            sic="1234",
            industry="Widgets",
            fiscal_year_end="1231",
            filer_category="large accelerated filer",
            is_company=True,
        )

    def ticker_rows(self):  # type: ignore[no-untyped-def]
        return self.rows

    def company(self, cik: int) -> Any:
        self.company_calls += 1
        return self.company_value

    def filings(self, company: Any, *, full: bool):  # type: ignore[no-untyped-def]
        self.filing_calls.append(full)
        return self.values


def filing(
    accession: str = "0000000001-26-000001",
    *,
    form: str = "10-K",
    filing_date: date = date(2026, 2, 1),
    report_date: date | None = date(2025, 12, 31),
    document: str | None = "example.htm",
    html: Any = "<html><body>filing</body></html>",
) -> Any:
    return SimpleNamespace(
        accession_number=accession,
        form=form,
        filing_date=filing_date,
        period_of_report=report_date,
        acceptance_datetime=datetime(2026, 2, 1, 12, 30),
        act="34",
        file_number="001-00001",
        size=1234,
        is_xbrl=True,
        is_inline_xbrl=True,
        document=document,
        primary_document_description="Annual report",
        homepage_url=f"https://www.sec.gov/Archives/{accession}-index.html",
        filing_url=f"https://www.sec.gov/Archives/{document}",
        text_url=f"https://www.sec.gov/Archives/{accession}.txt",
        sequence="1",
        html=lambda: html if not isinstance(html, Exception) else (_ for _ in ()).throw(html),
    )


def gateway(
    rows: list[dict[str, Any]] | None = None, filings: list[Any] | None = None
) -> tuple[EdgarGateway, FakeFacade]:
    facade = FakeFacade(rows or [{"ticker": "EX", "cik": 1, "company": "Example Corp"}], filings)
    return EdgarGateway(facade=facade), facade


def test_ticker_resolution_rejects_zero_and_multiple_distinct_ciks() -> None:
    missing, _ = gateway([{"ticker": "NOPE", "cik": 1}])
    with pytest.raises(UpstreamServiceError, match="absent"):
        missing.resolve("EX")
    ambiguous, _ = gateway([{"ticker": "EX", "cik": 1}, {"ticker": "EX", "cik": 2}])
    with pytest.raises(UpstreamServiceError, match="multiple"):
        ambiguous.resolve("ex")


def test_resolution_normalizes_enrichment_and_caches_company() -> None:
    value, facade = gateway()
    first = value.resolve(" ex ")
    second = value.resolve("EX")
    assert first is second
    assert first.cik == "0000000001"
    assert first.name == "Example Corp"
    assert first.tickers == ("EX",) and first.exchanges == ("NYSE",)
    assert first.sic == "1234" and first.industry == "Widgets"
    assert first.fiscal_year_end == "1231" and first.is_company is True
    assert facade.company_calls == 1


def test_original_filter_latest_historical_order_dedup_and_cache() -> None:
    old = filing("0000000001-24-000001", filing_date=date(2024, 2, 1), report_date=date(2023, 12, 31))
    latest = filing("0000000001-26-000001")
    duplicate = filing("0000000001-26-000001", filing_date=date(2026, 1, 31))
    amendment = filing("0000000001-26-000002", form="10-K/A")
    value, facade = gateway(filings=[old, amendment, duplicate, latest])
    _, _, candidates = value.discover_candidates("EX")
    assert [candidate.accession for candidate in candidates] == [
        latest.accession_number,
        old.accession_number,
    ]
    value.discover_candidates("EX")
    assert facade.filing_calls == [True]


def test_accession_is_revalidated_and_metadata_is_normalized() -> None:
    selected = filing()
    value, _ = gateway(filings=[selected])
    acquired = value.acquire("EX", accession=selected.accession_number, max_bytes=1000)
    assert acquired.filing.report_date == date(2025, 12, 31)
    assert acquired.filing.acceptance_datetime == datetime(2026, 2, 1, 12, 30)
    assert acquired.filing.primary_document_description == "Annual report"
    assert acquired.document.content == b"<html><body>filing</body></html>"
    assert acquired.document.media_type == "text/html"
    with pytest.raises(ValueError, match="not an original"):
        value.acquire("EX", accession="0000000001-26-999999", max_bytes=1000)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"report_date": None}, "report date"),
        ({"document": None}, "primary document"),
        ({"document": "example.txt"}, "not HTML"),
        ({"html": None}, "missing filing HTML"),
    ],
)
def test_missing_or_non_html_document_metadata_fails_safely(changes: dict[str, Any], message: str) -> None:
    value, _ = gateway(filings=[filing(**changes)])
    with pytest.raises(UpstreamServiceError):
        value.acquire("EX", max_bytes=1000)


def test_provider_failure_and_document_bound_are_safe() -> None:
    value, _ = gateway(filings=[filing(html=RuntimeError("secret provider detail"))])
    with pytest.raises(UpstreamServiceError, match="retrieval failed"):
        value.acquire("EX", max_bytes=1000)
    bounded, _ = gateway(filings=[filing(html="<html>" + "x" * 100 + "</html>")])
    with pytest.raises(UpstreamServiceError, match="size limit"):
        bounded.acquire("EX", max_bytes=20)


def test_acquisition_source_has_no_alternate_transport() -> None:
    source = Path("src/sec_filing_rag/integrations/sec.py").read_text(encoding="utf-8")
    forbidden = (
        "import httpx",
        "sec.gov/files",
        "data.sec.gov",
        "ElementTree",
        "submissions JSON",
        "urlopen",
    )
    assert not any(value in source for value in forbidden)


def test_bundled_edgartools_ticker_contract_maps_xom_without_network() -> None:
    from edgar import get_company_tickers

    rows = get_company_tickers()
    matches = rows.loc[rows["ticker"] == "XOM", "cik"].astype(int).unique().tolist()
    assert matches == [34088]


def test_discovery_ignores_acquisition_only_defects_in_legacy_filings() -> None:
    current = filing(
        "0000320193-24-000123",
        filing_date=date(2024, 11, 1),
        report_date=date(2024, 9, 28),
        document="aapl-20240928.htm",
    )
    legacy = [
        filing(
            f"0000320193-{year % 100:02d}-000001",
            filing_date=date(year, 12, 20),
            report_date=date(year, 9, 30),
            document=None,
        )
        for year in range(1994, 1999)
    ]
    value, _ = gateway(filings=[*legacy, current])

    _, _, candidates = value.discover_candidates("EX")

    assert candidates[0].accession == current.accession_number
    assert candidates[0].fiscal_year == 2024
    with pytest.raises(UpstreamServiceError):
        value.acquire("EX", accession=legacy[0].accession_number, max_bytes=1000)
