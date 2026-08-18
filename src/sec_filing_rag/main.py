from __future__ import annotations

import hmac
import uuid
from functools import lru_cache
from typing import Annotated, Any, Literal

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, field_validator

from .config import TICKER_RE, Settings, load_companies
from .domain import AnalysisPeriod
from .kestra import KestraGateway
from .models import DiscoveryRequest, PreparationAccepted, PreparationRequestBody
from .pipeline import BatchResult, IngestionPipeline
from .repositories import Database, FilingRepository, PreparationRepository
from .sec import EdgarGateway, configure_edgartools
from .services import FilingDiscoveryService, HistoricalPreparationService
from .store import Store


@lru_cache
def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def store() -> Store:
    return Store(settings().database_url)


def discovery_service() -> FilingDiscoveryService:
    config = settings()
    gateway = EdgarGateway(
        facade=configure_edgartools(
            config.edgar_identity, config.edgar_rate_limit_per_sec, config.edgar_access_mode
        )
    )
    return FilingDiscoveryService(
        gateway, FilingRepository(Database(config.database_url)), config.historical_filing_lookback_years
    )


def preparation_service() -> HistoricalPreparationService:
    config = settings()
    return HistoricalPreparationService(
        discovery_service(),
        PreparationRepository(Database(config.database_url)),
        KestraGateway(
            api_url=config.kestra_api_url,
            namespace=config.kestra_namespace,
            flow_id=config.kestra_historical_flow_id,
            username=config.kestra_basic_auth_username,
            password=config.kestra_basic_auth_password,
            timeout=config.kestra_timeout_seconds,
            retries=config.kestra_max_retries,
        ),
    )


def _configured_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if not TICKER_RE.fullmatch(normalized):
        raise HTTPException(status_code=422, detail="invalid ticker")
    configured = {entry.ticker: entry for entry in load_companies(settings().company_config_path).companies}
    entry = configured.get(normalized)
    if entry is None:
        raise HTTPException(status_code=404, detail="unknown configured ticker")
    if not entry.enabled:
        raise HTTPException(status_code=422, detail="configured ticker is disabled")
    return normalized


class IngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str = "all"
    trigger: Literal["manual", "schedule", "api", "historical"] = "api"
    preparation_request_id: uuid.UUID | None = None
    requested_year: int | None = None
    selected_accession: str | None = None
    kestra_execution_id: str | None = None

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
            CompanyIngestionResponse(**{**entry.__dict__, "run_id": str(entry.run_id)})
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

    @app.post("/api/companies/{ticker}/filings/discover")
    def discover_filing(
        ticker: str,
        request: DiscoveryRequest,
        service: Annotated[FilingDiscoveryService, Depends(discovery_service)],
    ) -> dict[str, Any]:
        normalized = _configured_ticker(ticker)
        try:
            period = AnalysisPeriod.year(request.period.value)
            return service.discover(normalized, period).response()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except Exception:
            raise HTTPException(
                status_code=502, detail="SEC filing discovery is temporarily unavailable"
            ) from None

    @app.post(
        "/api/companies/{ticker}/filings/prepare",
        response_model=PreparationAccepted,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def prepare_filing(
        ticker: str,
        request: PreparationRequestBody,
        service: Annotated[HistoricalPreparationService, Depends(preparation_service)],
    ) -> PreparationAccepted:
        normalized = _configured_ticker(ticker)
        try:
            request_id, execution_id = service.submit(
                normalized, AnalysisPeriod.year(request.period.value), request.confirmed_accession
            )
            return PreparationAccepted(request_id=request_id, execution_id=execution_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from None

    @app.post(
        "/internal/ingestions",
        response_model=IngestionResponse,
        dependencies=[Depends(authorize)],
    )
    def ingest(request: IngestionRequest, db: Annotated[Store, Depends(store)]) -> IngestionResponse:
        if not db.ready():
            raise HTTPException(status_code=503, detail="application database schema is not ready")
        config = load_companies(settings().company_config_path)
        enabled = {entry.ticker for entry in config.companies if entry.enabled}
        if request.target != "all" and request.target not in enabled:
            raise HTTPException(
                status_code=422, detail="target is unknown or disabled in company configuration"
            )
        if request.target == "all" and not enabled:
            raise HTTPException(status_code=422, detail="company configuration has no enabled targets")
        pipeline = IngestionPipeline(settings(), db)
        if request.trigger == "historical":
            if (
                request.target == "all"
                or request.preparation_request_id is None
                or request.requested_year is None
                or request.selected_accession is None
            ):
                raise HTTPException(status_code=422, detail="historical callback inputs are incomplete")
            return _response(
                pipeline.run_historical(
                    preparation_request_id=request.preparation_request_id,
                    ticker=request.target,
                    requested_year=request.requested_year,
                    selected_accession=request.selected_accession,
                    kestra_execution_id=request.kestra_execution_id,
                )
            )
        return _response(pipeline.run_batch(request.target, request.trigger, request.kestra_execution_id))

    return app


app = create_app()


def run() -> None:
    config = settings()
    uvicorn.run("sec_filing_rag.main:app", host=config.app_host, port=config.app_port)
