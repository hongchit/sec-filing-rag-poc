from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ItemExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kestra_execution_id: str | None = None


class FilingSelectionResponse(BaseModel):
    item_id: uuid.UUID
    status: Literal["selected", "skipped"]
    accession: str | None = None
    fiscal_year: int | None = None
    reason: str | None = None


class AcquisitionResponse(BaseModel):
    acquisition_id: uuid.UUID
    accession: str
    checksum: str
    media_type: Literal["text/html"] = "text/html"
    size: int


class CorpusExecutionResponse(BaseModel):
    item_id: uuid.UUID
    status: Literal["succeeded", "skipped", "failed"]
    corpus_version_id: uuid.UUID | None = None
    promoted: bool = False
    error: str | None = None


class ItemFailureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: str
    kestra_execution_id: str | None = None


class BatchFinalizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kestra_execution_id: str | None = None
