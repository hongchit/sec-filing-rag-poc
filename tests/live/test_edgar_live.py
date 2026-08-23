from __future__ import annotations

import os

import pytest

from sec_filing_rag.domain.filings import REQUIRED_ITEMS, extract_sections, sanitize_filing_html
from sec_filing_rag.integrations.sec import EdgarGateway, configure_edgartools

pytestmark = [
    pytest.mark.live_edgar,
    pytest.mark.skipif(os.getenv("LIVE_EDGAR") != "1", reason="set LIVE_EDGAR=1 to run SEC regressions"),
]

EXPECTED = {
    "MSFT": (
        "0001193125-26-323660",
        8_585_501,
        "4bcf2da2871acc19e32c5a62f36f6d83d6aae03cdc4aaa9a86a9a21ee8223f02",
    ),
    "JPM": (
        "0001628280-26-008131",
        12_927_325,
        "4d9febdbc2038dcdca8726053286df4cbbfd48885051cbd781efcc3becb66a23",
    ),
    "XOM": (
        "0000034088-26-000045",
        5_591_068,
        "3591db2246ab14c52465d32f69b459b000919c141a5656c81cf59acf0a805be8",
    ),
}


def gateway() -> EdgarGateway:
    return EdgarGateway(facade=configure_edgartools(os.environ["EDGAR_IDENTITY"], 6, "CAUTION"))


@pytest.mark.parametrize(("ticker", "expected"), EXPECTED.items())
def test_exact_filing_bytes_metadata_and_six_item_extraction(
    ticker: str, expected: tuple[str, int, str]
) -> None:
    accession, length, checksum = expected
    acquired = gateway().acquire(ticker, accession=accession, max_bytes=20_000_000)
    assert len(acquired.document.content) == length
    assert acquired.document.sha256 == checksum
    assert acquired.filing.report_date and acquired.filing.homepage_url
    assert acquired.filing.filing_url and acquired.filing.text_url
    sections = extract_sections(sanitize_filing_html(acquired.document.content, max_chars=20_000_000))
    assert tuple(sections) == REQUIRED_ITEMS
    assert all(section.status not in {"failed", "not_assessed"} for section in sections.values())


def test_tsla_amendment_is_excluded_and_original_is_eligible() -> None:
    _, _, candidates = gateway().discover_candidates("TSLA")
    accessions = {candidate.accession for candidate in candidates}
    assert "0001104659-26-053166" not in accessions
    assert "0001628280-26-003952" in accessions
