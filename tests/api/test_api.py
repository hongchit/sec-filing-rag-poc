from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

import anyio.to_thread
import httpx
import pytest
from fastapi import HTTPException

from sec_filing_rag.api.dependencies import (
    batch_service,
    company_repository,
    current_user,
    evaluation_overview,
    execution_service,
    scheduled_batch_service,
    system_repository,
    workflow_repository,
)
from sec_filing_rag.auth import Principal
from sec_filing_rag.core.config import Settings
from sec_filing_rag.main import create_app


class FakeSystemRepository:
    def ready(self) -> bool:
        return True


class FakeCompanyRepository:
    def list(self) -> list[dict[str, object]]:
        return [{"ticker": "AAPL", "resolution_status": "pending"}]

    def status(self, ticker: str) -> dict[str, object] | None:
        return {"ticker": ticker, "active_corpus": None, "coverage": [], "latest_run": None}


class FakeBatchService:
    def submit(self, *, tickers, fiscal_year, request_id):  # type: ignore[no-untyped-def]
        del request_id
        selected = ["AAPL", "MSFT"] if tickers is None else tickers
        return uuid.UUID(int=1), "execution-1", selected


class FakeScheduledBatchService:
    def create(  # type: ignore[no-untyped-def]
        self, *, tickers, fiscal_year, request_id, launcher_execution_id
    ):
        assert request_id == f"kestra-launcher:{launcher_execution_id}"
        selected = ["AAPL", "MSFT"] if tickers is None else tickers
        return uuid.UUID(int=3), selected


class FakeRepository:
    def batch(self, batch_id: uuid.UUID, *args, **kwargs):  # type: ignore[no-untyped-def]
        del args, kwargs
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


class FakeEvaluationOverview:
    def current(self):  # type: ignore[no-untyped-def]
        return {
            "benchmark": {"question_count": 96},
            "retrieval": {"hit_count": 95},
            "generation": {"relevant_count": 95},
            "models": [],
            "example": None,
            "warnings": [],
        }


class ApiClient:
    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        self.app = app

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:  # type: ignore[no-untyped-def]
        async def send() -> httpx.Response:
            original = anyio.to_thread.run_sync

            async def direct(function, *args, **options):  # type: ignore[no-untyped-def]
                del options
                return function(*args)

            anyio.to_thread.run_sync = direct
            try:
                transport = httpx.ASGITransport(app=self.app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://testserver"
                ) as api:
                    return await api.request(method, path, **kwargs)
            finally:
                anyio.to_thread.run_sync = original

        return asyncio.run(send())

    def get(self, path: str, **kwargs) -> httpx.Response:  # type: ignore[no-untyped-def]
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:  # type: ignore[no-untyped-def]
        return self.request("POST", path, **kwargs)


def client(tmp_path: Path) -> ApiClient:
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
    app = create_app(config)
    app.dependency_overrides[system_repository] = FakeSystemRepository
    app.dependency_overrides[company_repository] = FakeCompanyRepository
    app.dependency_overrides[batch_service] = FakeBatchService
    app.dependency_overrides[workflow_repository] = FakeRepository
    app.dependency_overrides[execution_service] = FakeExecutionService
    app.dependency_overrides[scheduled_batch_service] = FakeScheduledBatchService
    app.dependency_overrides[current_user] = lambda: Principal(
        uuid.UUID(int=2), "user@example.com", "Test User", False, "csrf"
    )
    return ApiClient(app)


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
    company = api.get("/api/companies/AAPL/status").json()
    assert "preparation_requests" not in company
    assert "latest_default_corpus" not in company
    assert {"active_corpus", "historical_corpora", "coverage", "latest_run"} <= company.keys()


def test_internal_routes_are_bearer_protected_and_obsolete_routes_are_absent(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    item_id = uuid.uuid4()
    path = f"/internal/providers/filing-items/{item_id}/selection"
    assert api.post(path, json={}).status_code == 401
    assert api.post(path, headers={"Authorization": "Bearer bad"}, json={}).status_code == 401
    response = api.post(path, headers={"Authorization": "Bearer 0123456789abcdef"}, json={})
    assert response.status_code == 200
    assert api.post("/internal/ingestions", json={}).status_code == 404
    assert api.post("/api/companies/AAPL/filings/prepare", json={}).status_code == 404


def test_scheduled_batch_requires_internal_auth_and_launcher_correlation(tmp_path: Path) -> None:
    api = client(tmp_path)
    path = "/internal/scheduled-filing-batches"
    assert api.post(path, json={}).status_code == 401
    headers = {
        "Authorization": "Bearer 0123456789abcdef",
        "X-Kestra-Execution-ID": "execution-3",
        "X-Request-ID": "kestra-launcher:execution-3",
    }
    response = api.post(path, headers=headers, json={})
    assert response.status_code == 201
    assert response.json() == {
        "batch_id": str(uuid.UUID(int=3)),
        "mode": "latest",
        "fiscal_year": None,
        "tickers": ["AAPL", "MSFT"],
        "status": "created",
    }
    assert (
        api.post(path, headers={"Authorization": headers["Authorization"]}, json={}).status_code
        == 422
    )
    assert api.post(path, headers=headers, json={"unexpected": True}).status_code == 422


def test_evaluation_overview_is_public_and_read_only(tmp_path: Path) -> None:
    api = client(tmp_path)
    api.app.dependency_overrides.pop(current_user)
    api.app.dependency_overrides[evaluation_overview] = FakeEvaluationOverview

    response = api.get("/api/evaluation-overview/current")

    assert response.status_code == 200
    assert response.json()["benchmark"]["question_count"] == 96
    assert api.post("/api/evaluation-overview/current", json={}).status_code == 405


def test_showcase_is_public_and_evaluation_details_require_authentication(tmp_path: Path) -> None:
    api = client(tmp_path)

    def reject_anonymous() -> None:
        raise HTTPException(status_code=401, detail={"code": "authentication_required"})

    api.app.dependency_overrides[current_user] = reject_anonymous

    assert api.get("/api/showcase").status_code == 200
    assert (
        api.get("/api/retrieval-evaluations/current/configurations/configuration/cases").status_code
        == 401
    )
    assert api.get("/api/retrieval-evaluations/current/chunks/chunk").status_code == 401
    assert api.get("/api/generation-evaluations/current/cases").status_code == 401
    assert api.get("/api/generation-evaluations/current/questions/question").status_code == 401
    assert api.get("/api/generation-evaluations/current/prompts/prompt").status_code == 401
    assert api.get("/api/generation-evaluations/current/chunks/chunk").status_code == 401


def test_routers_are_mounted_only_in_their_namespaces() -> None:
    routes = {route.path for route in create_app().routes}
    assert "/api/filing-batches" in routes
    assert "/internal/corpus-executions/{item_id}" in routes
    assert "/internal/scheduled-filing-batches" in routes
    assert "/api/retrieval-evaluations/current" in routes
    assert "/api/evaluation-overview/current" in routes
    assert "/api/showcase" in routes
    assert "/api/retrieval-evaluations/current/configurations/{configuration_id}/cases" in routes
    assert "/api/retrieval-evaluations/current/chunks/{chunk_id}" in routes
    assert "/api/generation-evaluations/current" in routes
    assert "/api/generation-evaluations/current/cases" in routes
    assert "/api/generation-evaluations/current/questions/{case_id}" in routes
    assert "/api/generation-evaluations/current/prompts/{prompt_id}" in routes
    assert "/api/generation-evaluations/current/chunks/{chunk_id}" in routes
    assert all(
        path.startswith(("/api", "/internal", "/openapi", "/docs", "/redoc")) for path in routes
    )


def test_production_frontend_serves_assets_and_spa_routes_without_hiding_missing_assets(
    tmp_path: Path,
) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<main>SEC Filing RAG</main>", encoding="utf-8")
    (frontend / "app.js").write_text("console.log('app')", encoding="utf-8")
    company_file = tmp_path / "companies.yaml"
    company_file.write_text("companies:\n  - ticker: AAPL\n    enabled: true\n", encoding="utf-8")
    config = Settings(
        ingestion_api_token="0123456789abcdef",
        edgar_identity="Test test@example.com",
        openai_api_key="key",
        company_config_path=company_file,
        frontend_dist_path=frontend,
    )
    api = ApiClient(create_app(config))
    api.app.dependency_overrides[system_repository] = FakeSystemRepository

    assert api.get("/").text == "<main>SEC Filing RAG</main>"
    assert api.get("/research/history").text == "<main>SEC Filing RAG</main>"
    assert api.get("/app.js").text == "console.log('app')"
    assert api.get("/missing.js").status_code == 404
    assert api.get("/api/missing").status_code == 404
    assert api.get("/internal/missing").status_code == 404
    assert api.get("/api/health").status_code == 200


def test_module_style_app_reads_frontend_path_from_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<main>Production</main>", encoding="utf-8")
    monkeypatch.setenv("FRONTEND_DIST_PATH", str(frontend))

    assert ApiClient(create_app()).get("/").text == "<main>Production</main>"
