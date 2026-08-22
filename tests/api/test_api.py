from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from sec_filing_rag.config import Settings
from sec_filing_rag.dependencies import (
    batch_service,
    execution_service,
    settings,
    store,
    workflow_repository,
)
from sec_filing_rag.main import create_app


class FakeStore:
    def ready(self) -> bool:
        return True

    def companies(self) -> list[dict[str, object]]:
        return [{"ticker": "AAPL", "resolution_status": "pending"}]

    def company_status(self, ticker: str) -> dict[str, object] | None:
        return {"ticker": ticker, "active_corpus": None, "coverage": [], "latest_run": None}


class FakeBatchService:
    def submit(self, *, tickers, fiscal_year, request_id):  # type: ignore[no-untyped-def]
        del request_id
        selected = ["AAPL", "MSFT"] if tickers is None else tickers
        return uuid.UUID(int=1), "execution-1", selected


class FakeRepository:
    def batch(self, batch_id: uuid.UUID):  # type: ignore[no-untyped-def]
        if batch_id.int != 1:
            return None
        now = datetime.now(UTC)
        return {
            "batch_id": batch_id,
            "kestra_execution_id": "execution-1",
            "request_id": "request-1",
            "mode": "latest",
            "fiscal_year": None,
            "status": "submitted",
            "items": [],
            "created_at": now,
            "updated_at": now,
        }


class FakeExecutionService:
    def select(self, item_id, execution_id):  # type: ignore[no-untyped-def]
        del item_id, execution_id
        return "0000320193-24-000123", 2024


def client(tmp_path: Path) -> TestClient:
    company_file = tmp_path / "companies.yaml"
    company_file.write_text(
        "companies:\n  - ticker: AAPL\n    enabled: true\n  - ticker: MSFT\n    enabled: true\n"
    )
    config = Settings(
        ingestion_api_token="0123456789abcdef",
        edgar_identity="Test test@example.com",
        openai_api_key="key",
        company_config_path=company_file,
    )
    app = create_app()
    app.dependency_overrides[settings] = lambda: config
    app.dependency_overrides[store] = FakeStore
    app.dependency_overrides[batch_service] = FakeBatchService
    app.dependency_overrides[workflow_repository] = FakeRepository
    app.dependency_overrides[execution_service] = FakeExecutionService
    return TestClient(app)


def test_public_batch_shapes_and_validation(tmp_path: Path) -> None:
    api = client(tmp_path)
    latest = api.post("/api/filing-batches", json={})
    assert latest.status_code == 202 and latest.json()["mode"] == "latest"
    exact = api.post("/api/filing-batches", json={"tickers": ["aapl"], "fiscal_year": 2024})
    assert exact.status_code == 202 and exact.json()["tickers"] == ["AAPL"]
    assert api.post("/api/filing-batches", json={"tickers": []}).status_code == 422
    assert api.post("/api/filing-batches", json={"tickers": ["AAPL", "aapl"]}).status_code == 422
    assert api.post("/api/companies/AAPL/filing-preparations", json={}).status_code == 202
    assert api.get(f"/api/filing-batches/{uuid.UUID(int=1)}").status_code == 200


def test_internal_routes_are_bearer_protected_and_obsolete_routes_are_absent(tmp_path: Path) -> None:
    api = client(tmp_path)
    item_id = uuid.uuid4()
    path = f"/internal/providers/filing-items/{item_id}/selection"
    assert api.post(path, json={}).status_code == 401
    assert api.post(path, headers={"Authorization": "Bearer bad"}, json={}).status_code == 401
    response = api.post(path, headers={"Authorization": "Bearer 0123456789abcdef"}, json={})
    assert response.status_code == 200
    assert api.post("/internal/ingestions", json={}).status_code == 404
    assert api.post("/api/companies/AAPL/filings/prepare", json={}).status_code == 404


def test_routers_are_mounted_only_in_their_namespaces() -> None:
    routes = {route.path for route in create_app().routes}
    assert "/api/filing-batches" in routes
    assert "/internal/corpus-executions/{item_id}" in routes
    assert all(path.startswith(("/api", "/internal", "/openapi", "/docs", "/redoc")) for path in routes)
