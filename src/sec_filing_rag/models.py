from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from .config import TICKER_RE


class AnalysisPeriodRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    granularity: Literal["year"]
    value: str

    @field_validator("value")
    @classmethod
    def four_digit_year(cls, value: str) -> str:
        if len(value) != 4 or not value.isascii() or not value.isdigit():
            raise ValueError("period value must be a four-digit year")
        return value


class DiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period: AnalysisPeriodRequest


class PreparationRequestBody(DiscoveryRequest):
    confirmed_accession: str | None = None


class FilingCandidateResponse(BaseModel):
    accession: str
    fiscal_year: int
    report_date: date
    filing_date: date
    ready: bool = False
    corpus_version_id: str | None = None


class DiscoveryResponse(BaseModel):
    ticker: str
    requested_period: AnalysisPeriodRequest
    lookback: dict[str, int]
    exact: FilingCandidateResponse | None
    earlier: FilingCandidateResponse | None
    later: FilingCandidateResponse | None


class PreparationAccepted(BaseModel):
    request_id: str
    execution_id: str
    status: Literal["submitted"] = "submitted"


def normalize_ticker(value: str) -> str:
    ticker = value.strip().upper()
    if not TICKER_RE.fullmatch(ticker):
        raise ValueError("invalid ticker")
    return ticker
