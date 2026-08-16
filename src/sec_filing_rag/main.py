from __future__ import annotations

import hmac
from functools import lru_cache
from typing import Annotated, Any, Literal

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, field_validator

from .config import TICKER_RE, Settings, load_companies
from .pipeline import BatchResult, IngestionPipeline
from .store import Store


@lru_cache
def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def store() -> Store:
    return Store(settings().database_url)


class IngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str = "all"
    trigger: Literal["manual", "schedule", "api"] = "api"

    @field_validator("target", mode="before")
    @classmethod
    def normalize(cls, value: object) -> str:
        target = str(value).strip()
        if target.lower() == "all":
            return "all"
        ticker = target.upper()
        if not TICKER_RE.fullmatch(ticker):
            raise ValueError("target must be 'all' or a valid 1-10 character ticker")
        return ticker


class CompanyIngestionResponse(BaseModel):
    ticker: str
    run_id: str
    outcome: Literal["succeeded", "skipped", "failed"]
    accession: str | None
    coverage: dict[str, str]
    section_count: int
    chunk_count: int
    search_document_count: int
    embedding_usage_status: str
    corpus_disposition: str
    error: str | None = None


class IngestionResponse(BaseModel):
    status: Literal["succeeded", "partial_failure", "failed"]
    results: list[CompanyIngestionResponse]


def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = f"Bearer {settings().ingestion_api_token}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid ingestion token")


def _response(result: BatchResult) -> IngestionResponse:
    return IngestionResponse(
        status=result.status,  # type: ignore[arg-type]
        results=[
            CompanyIngestionResponse(
                **{**entry.__dict__, "run_id": str(entry.run_id)}
            )
            for entry in result.results
        ],
    )


def create_app() -> FastAPI:
    app = FastAPI(title="SEC Filing RAG", version="0.1.0")

    @app.get("/api/health")
    def health(db: Annotated[Store, Depends(store)]) -> dict[str, str]:
        ready = db.ready()
        if not ready:
            raise HTTPException(
                status_code=503, detail={"process": "ok", "application_database": "unavailable"}
            )
        return {"process": "ok", "application_database": "ready"}

    @app.get("/api/companies")
    def companies(db: Annotated[Store, Depends(store)]) -> list[dict[str, Any]]:
        config = load_companies(settings().company_config_path)
        stored = {entry["ticker"]: entry for entry in db.companies()}
        result: list[dict[str, Any]] = []
        for entry in config.companies:
            row = stored.get(
                entry.ticker,
                {
                    "ticker": entry.ticker,
                    "cik": None,
                    "name": None,
                    "resolution_status": "pending",
                    "safe_error": None,
                    "accession": None,
                    "filing_date": None,
                    "corpus_status": None,
                    "ready_at": None,
                    "latest_run_status": "pending",
                },
            )
            result.append({**row, "enabled": entry.enabled})
        return result

    @app.get("/api/companies/{ticker}/status")
    def company_status(ticker: str, db: Annotated[Store, Depends(store)]) -> dict[str, Any]:
        normalized = ticker.strip().upper()
        if not TICKER_RE.fullmatch(normalized):
            raise HTTPException(status_code=422, detail="invalid ticker")
        config = load_companies(settings().company_config_path)
        configured = {entry.ticker: entry for entry in config.companies}
        if normalized not in configured:
            raise HTTPException(status_code=404, detail="unknown configured ticker")
        result = db.company_status(normalized)
        if result is None:
            entry = configured[normalized]
            return {
                "ticker": entry.ticker,
                "enabled": entry.enabled,
                "cik": None,
                "name": None,
                "resolution_status": "pending",
                "safe_error": None,
                "active_corpus": None,
                "coverage": [],
                "latest_run": None,
            }
        result["enabled"] = configured[normalized].enabled
        return result

    @app.post(
        "/internal/ingestions",
        response_model=IngestionResponse,
        dependencies=[Depends(authorize)],
    )
    def ingest(request: IngestionRequest, db: Annotated[Store, Depends(store)]) -> IngestionResponse:
        config = load_companies(settings().company_config_path)
        enabled = {entry.ticker for entry in config.companies if entry.enabled}
        if request.target != "all" and request.target not in enabled:
            raise HTTPException(
                status_code=422, detail="target is unknown or disabled in company configuration"
            )
        if request.target == "all" and not enabled:
            raise HTTPException(status_code=422, detail="company configuration has no enabled targets")
        return _response(IngestionPipeline(settings(), db).run_batch(request.target, request.trigger))

    return app


app = create_app()


def run() -> None:
    config = settings()
    uvicorn.run("sec_filing_rag.main:app", host=config.app_host, port=config.app_port)
