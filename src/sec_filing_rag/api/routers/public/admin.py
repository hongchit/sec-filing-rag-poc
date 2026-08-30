from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ....auth import AuthRepository, Principal
from ....core.config import Settings
from ....repositories.model_executions import ModelExecutionRepository
from ...dependencies import (
    auth_repository,
    model_execution_repository,
    require_admin,
    settings,
)

router = APIRouter(prefix="/admin", tags=["administration"])


class ModelOperation(BaseModel):
    operation: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    latency_ms: int | None
    usage_status: str
    normalized_status: str
    attempt: int
    retry_count: int
    provider_started_at: datetime | None
    provider_finished_at: datetime | None


class ModelExecution(BaseModel):
    run_type: Literal["retrieval_evaluation", "generation_evaluation", "ground_truth_generation"]
    id: uuid.UUID
    status: str
    safe_error: str | None
    started_at: datetime
    finished_at: datetime | None
    models: list[str]
    operations: list[ModelOperation]
    provider_calls: int
    retries: int
    failures: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    usage_available: bool
    estimate_status: Literal["available", "unavailable"]
    estimated_usd: Decimal | None
    pricing_basis: Literal["stored_snapshot", "current_price_estimate"]
    pricing_version: str | None
    pricing_sha256: str | None


class ModelExecutionPage(BaseModel):
    items: list[ModelExecution]
    total: int
    limit: int
    offset: int
    next_offset: int | None


@router.get("/model-executions")
def model_executions(
    repository: Annotated[ModelExecutionRepository, Depends(model_execution_repository)],
    _: Annotated[Principal, Depends(require_admin)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ModelExecutionPage:
    return ModelExecutionPage.model_validate(repository.list(limit=limit, offset=offset))


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["active", "disabled"] | None = None
    lifetime_budget_override_usd: Decimal | None = Field(default=None, ge=0)
    clear_budget_override: bool = False

    @model_validator(mode="after")
    def has_change(self) -> UserUpdate:
        if (
            self.status is None
            and self.lifetime_budget_override_usd is None
            and not self.clear_budget_override
        ):
            raise ValueError("at least one account change is required")
        if self.lifetime_budget_override_usd is not None and self.clear_budget_override:
            raise ValueError("budget override cannot be set and cleared together")
        return self


@router.get("/users")
def users(
    repository: Annotated[AuthRepository, Depends(auth_repository)],
    config: Annotated[Settings, Depends(settings)],
    _: Annotated[Principal, Depends(require_admin)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    search: str | None = None,
) -> dict[str, object]:
    return {
        "items": repository.users(
            limit=limit, search=search, default=config.default_user_lifetime_budget_usd
        )
    }


@router.get("/users/{user_id}/activity")
def activity(
    user_id: uuid.UUID,
    repository: Annotated[AuthRepository, Depends(auth_repository)],
    _: Annotated[Principal, Depends(require_admin)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
    value = repository.user_activity(user_id, limit=limit)
    if value is None:
        raise HTTPException(404, detail="user not found")
    return value


@router.patch("/users/{user_id}")
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    request: Request,
    repository: Annotated[AuthRepository, Depends(auth_repository)],
    admin: Annotated[Principal, Depends(require_admin)],
) -> dict[str, str]:
    if user_id == admin.id and body.status == "disabled":
        raise HTTPException(409, detail={"code": "cannot_disable_self"})
    if not repository.update_user(
        user_id,
        status=body.status,
        budget_override=body.lifetime_budget_override_usd,
        clear_budget_override=body.clear_budget_override,
    ):
        raise HTTPException(404, detail="user not found")
    repository.audit(
        "admin_user_update",
        "succeeded",
        actor=admin.id,
        target_type="user",
        target_id=str(user_id),
        request_id=getattr(request.state, "request_id", None),
        metadata={
            "status": body.status,
            "budget_changed": body.lifetime_budget_override_usd is not None
            or body.clear_budget_override,
        },
    )
    return {"status": "updated"}
