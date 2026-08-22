from __future__ import annotations

import json
import logging
import os
import re
import time
import traceback
import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any, cast

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response

from .dependencies import settings
from .errors import UpstreamServiceError
from .internal_api import router as internal_router
from .public_api import router as public_router

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_LOGGER = logging.getLogger("sec_filing_rag.api")
if not _LOGGER.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    _LOGGER.addHandler(handler)
_LOGGER.propagate = False
_LOGGER.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())


def _mark_error(request: Request, *, code: str, exc: BaseException, include_traceback: bool) -> None:
    request.state.error_code = code
    request.state.error = exc
    request.state.log_traceback = include_traceback


def _log_request(request: Request, status_code: int, duration_ms: float) -> None:
    route = request.scope.get("route")
    fields: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "severity": "ERROR" if status_code >= 500 else "WARNING" if status_code >= 400 else "INFO",
        "event": "api_request",
        "request_id": request.state.request_id,
        "method": request.method,
        "route": getattr(route, "path", request.url.path),
        "status": status_code,
        "error_code": getattr(request.state, "error_code", "request_succeeded"),
        "context": {
            "ticker": request.path_params.get("ticker"),
            "batch_id": request.path_params.get("batch_id"),
            "item_id": request.path_params.get("item_id"),
        },
        "duration_ms": round(duration_ms, 3),
    }
    error = getattr(request.state, "error", None)
    if error is not None and getattr(request.state, "log_traceback", False):
        fields["exception_types"] = [type(error).__name__]
        fields["stack"] = [
            {"file": frame.filename, "line": frame.lineno, "function": frame.name}
            for frame in traceback.extract_tb(error.__traceback__)
        ]
    _LOGGER.log(
        logging.ERROR if status_code >= 500 else logging.WARNING if status_code >= 400 else logging.INFO,
        json.dumps(fields, separators=(",", ":"), default=str),
    )


def create_app() -> FastAPI:
    app = FastAPI(title="SEC Filing RAG", version="0.2.0")

    @app.middleware("http")
    async def correlate_and_log(request: Request, call_next: Any) -> Response:
        started = time.perf_counter()
        incoming = request.headers.get("X-Request-ID", "")
        request.state.request_id = incoming if _REQUEST_ID_RE.fullmatch(incoming) else str(uuid.uuid4())
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            _mark_error(request, code="unexpected_server_error", exc=exc, include_traceback=True)
            response = JSONResponse(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR, content={"detail": "Internal server error"}
            )
        response.headers["X-Request-ID"] = request.state.request_id
        _log_request(request, response.status_code, (time.perf_counter() - started) * 1000)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> Response:
        _mark_error(request, code="request_validation_error", exc=exc, include_traceback=False)
        return cast(Response, await request_validation_exception_handler(request, exc))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> Response:
        _mark_error(request, code=f"http_{exc.status_code}", exc=exc, include_traceback=False)
        return await http_exception_handler(request, exc)

    @app.exception_handler(UpstreamServiceError)
    async def upstream_error(request: Request, exc: UpstreamServiceError) -> Response:
        _mark_error(request, code=exc.code, exc=exc, include_traceback=True)
        return JSONResponse(status_code=HTTPStatus.BAD_GATEWAY, content={"detail": exc.public_detail})

    app.include_router(public_router)
    app.include_router(internal_router)
    return app


app = create_app()


def run() -> None:
    config = settings()
    _LOGGER.setLevel(config.log_level)
    uvicorn.run("sec_filing_rag.main:app", host=config.app_host, port=config.app_port)
