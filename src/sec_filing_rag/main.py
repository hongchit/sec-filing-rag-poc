from __future__ import annotations

import hmac
from functools import lru_cache
from typing import Annotated, Literal

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, field_validator

from .config import Settings, load_companies
from .pipeline import IngestionPipeline, Result
from .store import Store


@lru_cache
def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def store() -> Store:
    return Store(settings().database_url)


class IngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str
    item: Literal["1A"]
    trigger: Literal["manual", "schedule", "api"] = "api"

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize(cls, value: object) -> str:
        return str(value).strip().upper()


class IngestionResponse(BaseModel):
    run_id: str
    ticker: str
    accession: str
    coverage_status: str
    chunk_count: int
    embedding_usage_status: str
    corpus_status: str


def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = f"Bearer {settings().ingestion_api_token}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid ingestion token")


def create_app() -> FastAPI:
    app = FastAPI(title="SEC Filing RAG", version="0.1.0")

    @app.get("/api/health")
    def health(db: Annotated[Store, Depends(store)]) -> dict[str, str]:
        ready = db.ready()
        if not ready:
            raise HTTPException(status_code=503, detail={"process": "ok", "application_database": "unavailable"})
        return {"process": "ok", "application_database": "ready"}

    @app.post("/internal/ingestions", response_model=IngestionResponse, dependencies=[Depends(authorize)])
    def ingest(request: IngestionRequest, db: Annotated[Store, Depends(store)]) -> IngestionResponse:
        configured = {entry.ticker for entry in load_companies(settings().company_config_path).companies if entry.enabled}
        if request.ticker not in configured:
            raise HTTPException(status_code=422, detail="ticker is not enabled in company configuration")
        try:
            result: Result = IngestionPipeline(settings(), db).run(request.ticker, request.item, request.trigger)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from None
        return IngestionResponse(**{**result.__dict__, "run_id": str(result.run_id)})

    return app


app = create_app()


def run() -> None:
    config = settings()
    uvicorn.run("sec_filing_rag.main:app", host=config.app_host, port=config.app_port)
