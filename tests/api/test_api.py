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


def test_health_and_authentication(monkeypatch, tmp_path: Path) -> None:
    company_file = tmp_path / "companies.yaml"
    company_file.write_text(
        "companies:\n  - ticker: AAPL\n    enabled: true\n  - ticker: MSFT\n    enabled: false\n"
    )
    fake_settings = Settings(ingestion_api_token="0123456789abcdef", sec_user_agent="Test test@example.com", openai_api_key="key", company_config_path=company_file)
    app = create_app()
    app.dependency_overrides[store] = FakeStore
    monkeypatch.setattr("sec_filing_rag.main.settings", lambda: fake_settings)
    client = TestClient(app)
    assert client.get("/api/health").json()["application_database"] == "ready"
    assert client.post("/internal/ingestions", json={"target": "AAPL"}).status_code == 401
    assert client.post("/internal/ingestions", headers={"Authorization": "Bearer bad"}, json={"target": "AAPL"}).status_code == 401
    assert client.post("/internal/ingestions", headers={"Authorization": "Bearer 0123456789abcdef"}, json={"target": "bad ticker"}).status_code == 422
    companies = client.get("/api/companies").json()
    assert [company["ticker"] for company in companies] == ["AAPL", "MSFT"]
    assert companies[1]["resolution_status"] == "pending"
    assert client.get("/api/companies/aapl/status").json()["ticker"] == "AAPL"
    pending = client.get("/api/companies/MSFT/status").json()
    assert pending["enabled"] is False and pending["active_corpus"] is None
    assert client.get("/api/companies/unknown/status").status_code == 404
    assert client.get("/api/companies/bad_ticker/status").status_code == 422
    settings.cache_clear()
