from pathlib import Path

from fastapi.testclient import TestClient

from sec_filing_rag.config import Settings
from sec_filing_rag.main import create_app, settings, store


class FakeStore:
    def ready(self) -> bool:
        return True

    def load_configuration(self, config, path) -> None:  # type: ignore[no-untyped-def]
        del config, path

    def companies(self) -> list[dict[str, object]]:
        return [{"ticker": "AAPL", "enabled": True, "resolution_status": "pending"}]

    def company_status(self, ticker: str) -> dict[str, object] | None:
        if ticker != "AAPL":
            return None
        return {"ticker": ticker, "enabled": True, "coverage": [], "active_corpus": None}


class NotReadyStore(FakeStore):
    def ready(self) -> bool:
        return False


def test_health_and_authentication(monkeypatch, tmp_path: Path) -> None:
    company_file = tmp_path / "companies.yaml"
    company_file.write_text(
        "companies:\n  - ticker: AAPL\n    enabled: true\n  - ticker: MSFT\n    enabled: false\n"
    )
    fake_settings = Settings(
        ingestion_api_token="0123456789abcdef",
        sec_user_agent="Test test@example.com",
        openai_api_key="key",
        company_config_path=company_file,
    )
    app = create_app()
    app.dependency_overrides[store] = FakeStore
    monkeypatch.setattr("sec_filing_rag.main.settings", lambda: fake_settings)
    client = TestClient(app)
    assert client.get("/api/health").json()["application_database"] == "ready"
    assert client.post("/internal/ingestions", json={"target": "AAPL"}).status_code == 401
    assert (
        client.post(
            "/internal/ingestions", headers={"Authorization": "Bearer bad"}, json={"target": "AAPL"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/internal/ingestions",
            headers={"Authorization": "Bearer 0123456789abcdef"},
            json={"target": "bad ticker"},
        ).status_code
        == 422
    )
    companies = client.get("/api/companies").json()
    assert [company["ticker"] for company in companies] == ["AAPL", "MSFT"]
    assert companies[1]["resolution_status"] == "pending"
    assert client.get("/api/companies/aapl/status").json()["ticker"] == "AAPL"
    pending = client.get("/api/companies/MSFT/status").json()
    assert pending["enabled"] is False and pending["active_corpus"] is None
    assert client.get("/api/companies/unknown/status").status_code == 404
    assert client.get("/api/companies/bad_ticker/status").status_code == 422
    settings.cache_clear()


def test_health_reports_unavailable_when_schema_is_not_ready() -> None:
    app = create_app()
    app.dependency_overrides[store] = NotReadyStore
    response = TestClient(app).get("/api/health")
    assert response.status_code == 503
    assert response.json()["detail"]["application_database"] == "unavailable"


def test_ingestion_rejects_unready_schema_before_pipeline(monkeypatch, tmp_path: Path) -> None:
    company_file = tmp_path / "companies.yaml"
    company_file.write_text("companies:\n  - ticker: AAPL\n    enabled: true\n")
    fake_settings = Settings(
        ingestion_api_token="0123456789abcdef",
        sec_user_agent="Test test@example.com",
        openai_api_key="key",
        company_config_path=company_file,
    )
    monkeypatch.setattr("sec_filing_rag.main.settings", lambda: fake_settings)

    def fail_pipeline(*args, **kwargs):  # type: ignore[no-untyped-def]
        del args, kwargs
        raise AssertionError("pipeline must not be constructed")

    monkeypatch.setattr("sec_filing_rag.main.IngestionPipeline", fail_pipeline)
    app = create_app()
    app.dependency_overrides[store] = NotReadyStore
    response = TestClient(app).post(
        "/internal/ingestions",
        headers={"Authorization": "Bearer 0123456789abcdef"},
        json={"target": "AAPL"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "application database schema is not ready"


def test_fiscal_routes_are_thin_and_return_accepted(monkeypatch, tmp_path: Path) -> None:
    from sec_filing_rag.main import discovery_service, preparation_service

    company_file = tmp_path / "companies.yaml"
    company_file.write_text("companies:\n  - ticker: XOM\n    enabled: true\n")
    fake_settings = Settings(
        ingestion_api_token="0123456789abcdef",
        sec_user_agent="Test test@example.com",
        openai_api_key="key",
        company_config_path=company_file,
    )

    class FakeDiscoveryResult:
        def response(self) -> dict[str, object]:
            return {
                "ticker": "XOM",
                "requested_period": {"granularity": "year", "value": "2024"},
                "lookback": {"earliest_year": 2016, "latest_year": 2025},
                "exact": {
                    "accession": "0000034088-25-000010",
                    "fiscal_year": 2024,
                    "report_date": "2024-12-31",
                    "filing_date": "2025-02-01",
                    "ready": False,
                    "corpus_version_id": None,
                },
                "earlier": None,
                "later": None,
            }

    class FakeDiscoveryService:
        def discover(self, ticker, period):  # type: ignore[no-untyped-def]
            assert ticker == "XOM" and period.value == 2024
            return FakeDiscoveryResult()

    class FakePreparationService:
        def submit(self, ticker, period, confirmed):  # type: ignore[no-untyped-def]
            assert (ticker, period.value, confirmed) == ("XOM", 2024, None)
            return "request-1", "execution-1"

    monkeypatch.setattr("sec_filing_rag.main.settings", lambda: fake_settings)
    app = create_app()
    app.dependency_overrides[discovery_service] = FakeDiscoveryService
    app.dependency_overrides[preparation_service] = FakePreparationService
    client = TestClient(app)
    payload = {"period": {"granularity": "year", "value": "2024"}}
    discovered = client.post("/api/companies/XOM/filings/discover", json=payload)
    assert discovered.status_code == 200
    assert discovered.json()["exact"]["filing_date"] == "2025-02-01"
    prepared = client.post("/api/companies/XOM/filings/prepare", json=payload)
    assert prepared.status_code == 202
    assert prepared.json() == {
        "request_id": "request-1",
        "execution_id": "execution-1",
        "status": "submitted",
    }
    assert (
        client.post(
            "/api/companies/XOM/filings/discover",
            json={"period": {"granularity": "quarter", "value": "2024"}},
        ).status_code
        == 422
    )
