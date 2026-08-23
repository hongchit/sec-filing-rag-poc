from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    process: Literal["ok"] = "ok"
    application_database: Literal["ready"] = "ready"


class StatusResponse(BaseModel):
    status: str
