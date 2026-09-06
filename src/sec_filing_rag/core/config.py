from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
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
    database_url: str = "postgresql://__required__:__required__@localhost/__required__"
    database_pool_min_size: int = Field(default=1, ge=1)
    database_pool_max_size: int = Field(default=10, ge=1)
    database_pool_timeout_seconds: float = Field(default=10, gt=0, le=60)
    database_startup_timeout_seconds: float = Field(default=10, gt=0, le=60)
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    ingestion_api_token: str = Field(min_length=16)
    company_config_path: Path = Path("config/companies.yaml")
    edgar_identity: str = Field(min_length=8)
    edgar_rate_limit_per_sec: int = Field(default=6, ge=1, le=10)
    edgar_access_mode: str = Field(default="CAUTION", pattern="^CAUTION$")
    max_filing_document_bytes: int = Field(default=50_000_000, ge=1_000_000, le=100_000_000)
    max_filing_narrative_chars: int = Field(default=20_000_000, ge=500_000, le=50_000_000)
    kestra_api_url: str = "http://kestra:8080/api/v1/main"
    kestra_namespace: str = "sec_filings.ingestion"
    kestra_batch_flow_id: str = "filing_batch"
    kestra_basic_auth_username: str = "__required__"
    kestra_basic_auth_password: str = Field(default="__required__", min_length=8)
    kestra_timeout_seconds: float = Field(default=10, gt=0, le=60)
    kestra_max_retries: int = Field(default=2, ge=0, le=5)
    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = Field(default=1536, gt=0)
    openai_chat_model: str = "gpt-5.4-mini"
    openai_judge_model: str | None = None
    openai_timeout_seconds: float = Field(default=30, gt=0, le=120)
    chunk_size_chars: int = Field(default=2400, ge=500, le=8000)
    chunk_overlap_chars: int = Field(default=240, ge=0, le=1000)
    parser_version: str = "corpus-heading-sanitized-v2"
    chunking_version: str = "character-v1"
    index_version: str = "vector-v1"
    retrieval_config_path: Path = Path("config/retrieval.json")
    retrieval_evaluation_result_path: Path = Path("evaluation/results/retrieval-v1.json")
    retrieval_evaluation_dataset_path: Path = Path("evaluation/retrieval-v1.jsonl")
    retrieval_evaluation_manifest_path: Path = Path("evaluation/retrieval-v1-manifest.json")
    generation_config_path: Path = Path("config/generation.json")
    generation_evaluation_result_path: Path = Path("evaluation/results/generation-v1.json")
    model_pricing_config_path: Path = Path("config/model-pricing-v1.json")
    showcase_config_path: Path = Path("config/showcase.json")
    public_base_url: str = "http://localhost:8000"
    google_client_id: str = "__required__"
    google_client_secret: str = "__required__"
    session_secret: str = Field(
        default="__required_session_secret_at_least_32_chars__", min_length=32
    )
    google_admin_emails: str = "admin@example.com"
    session_lifetime_days: int = Field(default=7, ge=1, le=30)
    default_user_lifetime_budget_usd: Decimal = Field(default=Decimal("1.00"), ge=0)
    research_cost_reservation_usd: Decimal = Field(default=Decimal("0.10"), gt=0)
    corpus_preparation_cost_reservation_usd: Decimal = Field(default=Decimal("0.50"), gt=0)

    @property
    def admin_emails(self) -> frozenset[str]:
        return frozenset(
            value.strip().lower() for value in self.google_admin_emails.split(",") if value.strip()
        )

    @property
    def primary_admin_email(self) -> str:
        """Return the configured cost owner for unattended ingestion."""
        return next(
            value.strip().lower() for value in self.google_admin_emails.split(",") if value.strip()
        )

    @property
    def resolved_judge_model(self) -> str:
        return self.openai_judge_model or self.openai_chat_model

    @field_validator("database_pool_max_size")
    @classmethod
    def valid_database_pool_range(cls, value: int, info: Any) -> int:
        minimum = info.data.get("database_pool_min_size", 1)
        if value < minimum:
            raise ValueError("database_pool_max_size must be at least database_pool_min_size")
        return value


class SessionSettings(BaseSettings):
    """Load middleware settings without requiring the complete application configuration."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    public_base_url: str = "http://localhost:8000"
    session_secret: str = "development-only-session-secret"
