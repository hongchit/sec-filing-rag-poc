from datetime import date

import pytest
from pydantic import ValidationError

from sec_filing_rag.config import CompanyConfiguration
from sec_filing_rag.domain import (
    compatibility_key,
    extract_item_1a,
    latest_original_10k,
    make_chunks,
    safe_error,
    sha256_bytes,
)


def test_company_configuration_normalizes_and_sorts() -> None:
    config = CompanyConfiguration.model_validate({"companies": [{"ticker": "msft"}, {"ticker": " AAPL "}]})
    assert [entry.ticker for entry in config.companies] == ["AAPL", "MSFT"]
    assert config.sha256() == CompanyConfiguration.model_validate(config.normalized()).sha256()


@pytest.mark.parametrize("companies", [[{"ticker": "AAPL"}, {"ticker": "aapl"}], [{"ticker": "bad ticker"}]])
def test_company_configuration_rejects_duplicates_and_invalid(companies: list[dict[str, str]]) -> None:
    with pytest.raises(ValidationError):
        CompanyConfiguration.model_validate({"companies": companies})


def test_selects_latest_exact_original_10k() -> None:
    recent = {"form": ["10-K/A", "10-K", "10-K"], "accessionNumber": ["a", "old", "new"],
              "primaryDocument": ["a.htm", "old.htm", "new.htm"], "filingDate": ["2026-04-01", "2024-01-01", "2025-01-01"],
              "reportDate": ["2025-12-31", "2023-12-31", "2024-12-31"]}
    selected = latest_original_10k(recent)
    assert selected.accession == "new"
    assert selected.filing_date == date(2025, 1, 1)


def test_item_1a_prefers_long_section_over_toc() -> None:
    text = "Item 1A. Risk Factors\npage 12\nItem 1B.\n" + "intro\nItem 1A. Risk Factors\n" + ("Material risk disclosure. " * 30) + "\nItem 1B. Unresolved Staff Comments"
    section = extract_item_1a(text)
    assert section.status == "present"
    assert section.text and "Material risk" in section.text


def test_explicit_coverage_outcomes() -> None:
    assert extract_item_1a("Item 1. Business").status == "legitimately_absent"
    assert extract_item_1a("Item 1A. Risk Factors\nno ending" ).status == "failed"


def test_deterministic_chunks_citations_and_checksums() -> None:
    first = make_chunks("word " * 1000, accession="0001-26-000001", item="1A", version="v1", size=500, overlap=50)
    second = make_chunks("word " * 1000, accession="0001-26-000001", item="1A", version="v1", size=500, overlap=50)
    assert first == second
    assert first[0].citation == "0001-26-000001:item-1a:0000"
    assert first[0].sha256 == sha256_bytes(first[0].text.encode())


def test_compatibility_key_is_canonical_and_redaction_is_safe() -> None:
    key = compatibility_key(parser="p", chunker="c", model="m", dimensions=3, index="i")
    assert len(key) == 64
    assert "secret" not in safe_error("secret for person@example.com", ("secret",))
