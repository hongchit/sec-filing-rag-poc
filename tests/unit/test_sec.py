import json
from datetime import date

from sec_filing_rag.domain import FilingCandidate
from sec_filing_rag.sec import BROWSE_ROOT, SUBMISSIONS_ROOT, TICKERS_URL, Fetched, SecClient


def _filings(forms: list[str], accessions: list[str]) -> dict[str, list[str]]:
    return {
        "form": forms,
        "accessionNumber": accessions,
        "primaryDocument": [f"{value}.htm" for value in accessions],
        "filingDate": ["2026-01-01" for _ in forms],
        "reportDate": ["2025-12-31" for _ in forms],
    }


def test_latest_filing_falls_back_to_sanitized_historical_submission_name(monkeypatch) -> None:
    current = {
        "filings": {
            "recent": _filings(["8-K"], ["recent"]),
            "files": [
                {"name": "../../unsafe.json"},
                {"name": "CIK0000034088-submissions-001.json"},
            ],
        }
    }
    historical = _filings(["10-K/A", "10-K"], ["amended", "original"])
    responses = {
        f"{SUBMISSIONS_ROOT}/CIK0000034088.json": current,
        f"{SUBMISSIONS_ROOT}/CIK0000034088-submissions-001.json": historical,
    }
    client = SecClient(identity="Test test@example.com", timeout=1, retries=0, interval=0.1)

    def fake_fetch(url: str) -> Fetched:
        body = json.dumps(responses[url]).encode()
        return Fetched(url, body, 200, {"content-type": "application/json"})

    monkeypatch.setattr(client, "fetch", fake_fetch)
    filing, fetched, payload = client.latest_filing("0000034088")
    assert filing.accession == "original"
    assert fetched.url.endswith("submissions-001.json")
    assert payload == historical


def test_latest_filing_uses_validated_atom_and_exact_10k_document(monkeypatch) -> None:
    current = {"filings": {"recent": _filings(["8-K"], ["recent"]), "files": []}}
    atom_url = f"{BROWSE_ROOT}?action=getcompany&CIK=0000034088&type=10-K&owner=exclude&output=atom&count=40"
    index_url = (
        "https://www.sec.gov/Archives/edgar/data/34088/000003408826000045/0000034088-26-000045-index.htm"
    )
    atom = f"""<feed><entry><filing-type>10-K/A</filing-type></entry><entry>
      <filing-type>10-K</filing-type><filing-date>2026-02-18</filing-date><period>20251231</period>
      <accession-number>0000034088-26-000045</accession-number><filing-href>{index_url}</filing-href>
    </entry></feed>"""
    index = """<table><tr><td>1</td><td><a href="xom-20251231.htm">FORM 10-K</a></td>
      <td>10-K</td></tr><tr><td><a href="evil.htm">other</a></td><td>10-K/A</td></tr></table>"""
    responses: dict[str, bytes] = {
        f"{SUBMISSIONS_ROOT}/CIK0000034088.json": json.dumps(current).encode(),
        atom_url: atom.encode(),
        index_url: index.encode(),
    }
    client = SecClient(identity="Test test@example.com", timeout=1, retries=0, interval=0.1)

    def fake_fetch(url: str) -> Fetched:
        return Fetched(url, responses[url], 200, {"content-type": "text/html"})

    monkeypatch.setattr(client, "fetch", fake_fetch)
    filing, fetched, payload = client.latest_filing("0000034088")
    assert filing.accession == "0000034088-26-000045"
    assert filing.primary_document == "xom-20251231.htm"
    assert filing.report_date and filing.report_date.isoformat() == "2025-12-31"
    assert fetched.url.endswith("CIK0000034088.json") and payload == current


def test_duplicate_ticker_selects_issuer_with_latest_original_10k(monkeypatch) -> None:
    tickers = {
        "0": {"ticker": "XOM", "cik_str": 2115436, "title": "ExxonMobil Holdings Corp"},
        "1": {"ticker": "XOM", "cik_str": 34088, "title": "Exxon Mobil Corp"},
    }
    ticker_fetch = Fetched(TICKERS_URL, json.dumps(tickers).encode(), 200, {})
    client = SecClient(identity="Test test@example.com", timeout=1, retries=0, interval=0.1)
    monkeypatch.setattr(client, "fetch", lambda url: ticker_fetch)

    def fake_latest(cik: str):  # type: ignore[no-untyped-def]
        if cik == "0002115436":
            raise ValueError("no original 10-K filing found")
        filing = FilingCandidate("0000034088-26-000045", "xom.htm", date(2026, 2, 18), None)
        return filing, Fetched("submission", b"{}", 200, {}), {}

    monkeypatch.setattr(client, "latest_filing", fake_latest)
    cik, name, fetched = client.resolve("XOM")
    assert cik == "0000034088" and name == "Exxon Mobil Corp"
    assert fetched is ticker_fetch


def test_ticker_atom_recovers_legacy_filer_missing_from_ticker_metadata(monkeypatch) -> None:
    tickers = {
        "0": {"ticker": "XOM", "cik_str": 2115436, "title": "ExxonMobil Holdings Corp"},
    }
    ticker_fetch = Fetched(TICKERS_URL, json.dumps(tickers).encode(), 200, {})
    atom_url = f"{BROWSE_ROOT}?action=getcompany&CIK=XOM&type=10-K&owner=exclude&output=atom&count=40"
    atom = b"""<feed><company-info><conformed-name>EXXON MOBIL CORP</conformed-name></company-info>
      <entry><filing-type>10-K</filing-type><filing-date>2026-02-18</filing-date>
      <accession-number>0000034088-26-000045</accession-number>
      <filing-href>https://www.sec.gov/Archives/edgar/data/34088/000003408826000045/0000034088-26-000045-index.htm</filing-href>
      </entry></feed>"""
    client = SecClient(identity="Test test@example.com", timeout=1, retries=0, interval=0.1)
    monkeypatch.setattr(
        client,
        "fetch",
        lambda url: ticker_fetch if url == TICKERS_URL else Fetched(atom_url, atom, 200, {}),
    )

    def fake_latest(cik: str):  # type: ignore[no-untyped-def]
        if cik == "0002115436":
            raise ValueError("no original 10-K filing found")
        filing = FilingCandidate("0000034088-26-000045", "xom.htm", date(2026, 2, 18), None)
        return filing, Fetched("submission", b"{}", 200, {}), {}

    monkeypatch.setattr(client, "latest_filing", fake_latest)
    cik, name, fetched = client.resolve("XOM")
    assert cik == "0000034088" and name == "EXXON MOBIL CORP"
    assert fetched is ticker_fetch
