from __future__ import annotations

import base64
import json
import queue
import threading
import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from ....auth import Principal, QuotaExceeded
from ....generation.service import (
    IdempotencyConflict,
    ResearchFailure,
    ResearchInProgress,
    ResearchRequest,
    ResearchService,
)
from ....schemas.research import ResearchCreate, ResearchHistory, ResearchResponse
from ...dependencies import current_user, research_service

router = APIRouter(prefix="/research", tags=["research"])


def _run(
    body: ResearchCreate,
    service: ResearchService,
    idempotency_key: uuid.UUID | None,
    on_stage: Any = None,
) -> dict[str, Any]:
    request = ResearchRequest.model_validate(body.model_dump())
    return service.create(request, idempotency_key=idempotency_key, on_stage=on_stage)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, QuotaExceeded):
        return HTTPException(403, detail={"code": "quota_exceeded", "budget": exc.summary})
    if isinstance(exc, IdempotencyConflict):
        return HTTPException(409, detail={"code": "idempotency_conflict"})
    if isinstance(exc, ResearchInProgress):
        return HTTPException(
            409, detail={"code": "research_in_progress", "research_id": str(exc.research_id)}
        )
    if isinstance(exc, ResearchFailure):
        return HTTPException(
            502, detail={"code": "answer_generation_failed", "research_id": str(exc.research_id)}
        )
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("", response_model=ResearchResponse, status_code=status.HTTP_201_CREATED)
def create_research(
    body: ResearchCreate,
    service: Annotated[ResearchService, Depends(research_service)],
    idempotency_key: Annotated[uuid.UUID | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    try:
        return _run(body, service, idempotency_key)
    except (
        ResearchFailure,
        ResearchInProgress,
        IdempotencyConflict,
        QuotaExceeded,
        ValueError,
    ) as exc:
        raise _http_error(exc) from None


@router.post("/stream", response_class=StreamingResponse)
def stream_research(
    body: ResearchCreate,
    service: Annotated[ResearchService, Depends(research_service)],
    idempotency_key: Annotated[uuid.UUID | None, Header(alias="Idempotency-Key")] = None,
) -> StreamingResponse:
    events: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue(maxsize=32)

    def publish(name: str, payload: dict[str, Any]) -> None:
        try:
            events.put_nowait((name, payload))
        except queue.Full:
            pass

    def produce() -> None:
        try:
            result = _run(body, service, idempotency_key, publish)
            publish("succeeded", ResearchResponse.model_validate(result).model_dump(mode="json"))
        except (
            ResearchFailure,
            ResearchInProgress,
            IdempotencyConflict,
            QuotaExceeded,
            ValueError,
        ) as exc:
            error = _http_error(exc)
            detail = error.detail if isinstance(error.detail, dict) else {"code": "invalid_request"}
            publish("failed", detail)
        finally:
            try:
                events.put_nowait(None)
            except queue.Full:
                pass

    threading.Thread(target=produce, name="research-stream", daemon=True).start()

    def generate() -> Iterator[str]:
        while True:
            event = events.get()
            if event is None:
                return
            name, payload = event
            yield f"event: {name}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history", response_model=ResearchHistory)
def research_history(
    service: Annotated[ResearchService, Depends(research_service)],
    user: Annotated[Principal, Depends(current_user)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: str | None = None,
) -> dict[str, Any]:
    decoded: tuple[datetime, uuid.UUID] | None = None
    if cursor:
        try:
            created, identifier = json.loads(base64.urlsafe_b64decode(cursor + "===").decode())
            decoded = datetime.fromisoformat(created), uuid.UUID(identifier)
        except Exception:
            raise HTTPException(422, detail="invalid cursor") from None
    items = service.repository.history(limit=limit + 1, cursor=decoded, user_id=user.id)  # type: ignore[attr-defined]
    next_cursor = None
    if len(items) > limit:
        last = items[limit - 1]
        token = json.dumps([last["created_at"].isoformat(), str(last["research_id"])]).encode()
        next_cursor = base64.urlsafe_b64encode(token).decode().rstrip("=")
        items = items[:limit]
    return {"items": items, "next_cursor": next_cursor}


@router.get("/{research_id}", response_model=ResearchResponse)
def get_research(
    research_id: uuid.UUID,
    service: Annotated[ResearchService, Depends(research_service)],
    user: Annotated[Principal, Depends(current_user)],
) -> dict[str, Any]:
    value = service.repository.get(research_id, user.id, is_admin=user.is_admin)
    if value is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="research not found")
    return value
