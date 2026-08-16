from pathlib import Path

from fastapi.testclient import TestClient

from sec_filing_rag.config import Settings
from sec_filing_rag.main import create_app, settings, store


class FakeStore:
    def ready(self) -> bool:
        return True


def test_health_and_authentication(monkeypatch, tmp_path: Path) -> None:
    company_file = tmp_path / "companies.yaml"
    company_file.write_text("companies:\n  - ticker: AAPL\n    enabled: true\n")
    fake_settings = Settings(ingestion_api_token="0123456789abcdef", sec_user_agent="Test test@example.com", openai_api_key="key", company_config_path=company_file)
    app = create_app()
    app.dependency_overrides[store] = FakeStore
    monkeypatch.setattr("sec_filing_rag.main.settings", lambda: fake_settings)
    client = TestClient(app)
    assert client.get("/api/health").json()["application_database"] == "ready"
    assert client.post("/internal/ingestions", json={"ticker": "AAPL", "item": "1A"}).status_code == 401
    assert client.post("/internal/ingestions", headers={"Authorization": "Bearer bad"}, json={"ticker": "AAPL", "item": "1A"}).status_code == 401
    assert client.post("/internal/ingestions", headers={"Authorization": "Bearer 0123456789abcdef"}, json={"ticker": "AAPL", "item": "7"}).status_code == 422
    settings.cache_clear()
