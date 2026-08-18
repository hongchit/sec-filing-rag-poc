from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


class CompanyEntry(BaseModel):
    ticker: str
    enabled: bool = True

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value: object) -> str:
        ticker = str(value).strip().upper()
        if not TICKER_RE.fullmatch(ticker):
            raise ValueError("ticker must contain 1-10 uppercase letters, digits, dot, or hyphen")
        return ticker


class CompanyConfiguration(BaseModel):
    companies: list[CompanyEntry]

    @field_validator("companies")
    @classmethod
    def unique_tickers(cls, value: list[CompanyEntry]) -> list[CompanyEntry]:
        tickers = [entry.ticker for entry in value]
        if len(tickers) != len(set(tickers)):
            raise ValueError("duplicate ticker")
        return value

    def normalized(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def sha256(self) -> str:
        raw = json.dumps(self.normalized(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()


def load_companies(path: Path) -> CompanyConfiguration:
    return CompanyConfiguration.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql://postgres:postgres@db:5432/sec_filings"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    ingestion_api_token: str = Field(min_length=16)
    company_config_path: Path = Path("config/companies.yaml")
    edgar_identity: str = Field(min_length=8)
    edgar_rate_limit_per_sec: int = Field(default=6, ge=1, le=10)
    edgar_access_mode: str = Field(default="CAUTION", pattern="^CAUTION$")
    max_filing_document_bytes: int = Field(default=50_000_000, ge=1_000_000, le=100_000_000)
    max_filing_narrative_chars: int = Field(default=20_000_000, ge=500_000, le=50_000_000)
    historical_filing_lookback_years: int = Field(default=10, ge=1, le=50)
    kestra_api_url: str = "http://kestra:8080/api/v1/main"
    kestra_namespace: str = "sec_filings.ingestion"
    kestra_historical_flow_id: str = "prepare_historical_filing"
    kestra_basic_auth_username: str = "admin@example.com"
    kestra_basic_auth_password: str = Field(default="ChangeMe1234", min_length=8)
    kestra_timeout_seconds: float = Field(default=10, gt=0, le=60)
    kestra_max_retries: int = Field(default=2, ge=0, le=5)
    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = Field(default=1536, gt=0)
    openai_timeout_seconds: float = Field(default=30, gt=0, le=120)
    chunk_size_chars: int = Field(default=2400, ge=500, le=8000)
    chunk_overlap_chars: int = Field(default=240, ge=0, le=1000)
    parser_version: str = "corpus-heading-sanitized-v2"
    chunking_version: str = "character-v1"
    index_version: str = "vector-v1"
    retrieval_config_path: Path = Path("config/retrieval.json")
