from __future__ import annotations

import json
import logging
import re
import time
import traceback
import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response

from .errors import UpstreamServiceError

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
LOGGER = logging.getLogger("sec_filing_rag.api")


def configure_logging(level: str) -> None:
    if not LOGGER.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        LOGGER.addHandler(handler)
    LOGGER.propagate = False
    LOGGER.setLevel(level)


def _mark_error(
    request: Request, *, code: str, exc: BaseException, include_traceback: bool
) -> None:
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
    LOGGER.log(
        logging.ERROR
        if status_code >= 500
        else logging.WARNING
        if status_code >= 400
        else logging.INFO,
        json.dumps(fields, separators=(",", ":"), default=str),
    )


def install_observability(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlate_and_log(request: Request, call_next: Any) -> Response:
        started = time.perf_counter()
        incoming = request.headers.get("X-Request-ID", "")
        request.state.request_id = (
            incoming if _REQUEST_ID_RE.fullmatch(incoming) else str(uuid.uuid4())
        )
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            _mark_error(request, code="unexpected_server_error", exc=exc, include_traceback=True)
            response = JSONResponse(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error"},
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
        return JSONResponse(
            status_code=HTTPStatus.BAD_GATEWAY, content={"detail": exc.public_detail}
        )
