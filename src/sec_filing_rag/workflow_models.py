from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import normalize_ticker

WorkflowMode = Literal["latest", "exact_year"]
BatchStatus = Literal["submitted", "running", "succeeded", "partial_failure", "failed"]
ItemStatus = Literal["pending", "selecting", "acquiring", "processing", "succeeded", "skipped", "failed"]


class FilingPreparationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fiscal_year: int | None = Field(default=None, ge=1900, le=9999)


class FilingBatchRequest(FilingPreparationRequest):
    tickers: list[str] | None = None

    @field_validator("tickers")
    @classmethod
    def normalize_tickers(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        if not values:
            raise ValueError("tickers must not be empty when supplied")
        normalized = [normalize_ticker(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("tickers must not contain duplicates")
        return normalized


class FilingBatchAccepted(BaseModel):
    batch_id: uuid.UUID
    kestra_execution_id: str
    mode: WorkflowMode
    fiscal_year: int | None
    tickers: list[str]
    status: Literal["submitted"] = "submitted"


class FilingBatchItemStatus(BaseModel):
    id: uuid.UUID
    position: int
    ticker: str
    status: ItemStatus
    selected_accession: str | None = None
    acquisition_id: uuid.UUID | None = None
    corpus_version_id: uuid.UUID | None = None
    safe_error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class FilingBatchStatus(BaseModel):
    batch_id: uuid.UUID
    kestra_execution_id: str | None
    request_id: str | None
    mode: WorkflowMode
    fiscal_year: int | None
    status: BatchStatus
    items: list[FilingBatchItemStatus]
    created_at: datetime
    updated_at: datetime
