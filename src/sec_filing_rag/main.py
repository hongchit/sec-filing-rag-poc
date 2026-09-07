from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from starlette.types import Scope

from .api.dependencies import settings
from .api.routers.internal import router as internal_router
from .api.routers.public import router as public_router
from .core.config import SessionSettings, Settings
from .core.observability import LOGGER, configure_logging, install_observability
from .core.resources import AppResources, StartupSchemaError, create_resources
from .core.startup import StartupConfigurationError, safe_startup_event

ResourceFactory = Callable[[Settings], AppResources]


class SPAStaticFiles(StaticFiles):
    """Serve index.html for client-side routes without hiding missing asset errors."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            normalized = path.lstrip("/")
            reserved = normalized == "api" or normalized.startswith(("api/", "internal/"))
            if exc.status_code != 404 or reserved or "." in path.rsplit("/", 1)[-1]:
                raise
            return await super().get_response("index.html", scope)


def create_app(
    config: Settings | None = None, *, resource_factory: ResourceFactory = create_resources
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            selected = config or settings()
        except ValidationError as exc:
            configure_logging("INFO")
            issues = [
                {
                    "code": "setting_invalid",
                    "category": str(error.get("loc", ("settings",))[0]),
                    "explanation": "A required setting is missing or invalid.",
                    "remediation": "Correct the named environment setting.",
                }
                for error in exc.errors(
                    include_input=False, include_context=False, include_url=False
                )
            ]
            LOGGER.error(safe_startup_event("startup_configuration_invalid", issues=issues))
            raise RuntimeError("startup configuration is invalid") from None
        configure_logging(selected.log_level)
        try:
            app.state.resources = resource_factory(selected)
        except StartupConfigurationError as exc:
            LOGGER.error(
                safe_startup_event(
                    "startup_configuration_invalid", issues=[issue.__dict__ for issue in exc.issues]
                )
            )
            raise RuntimeError("startup configuration is invalid") from None
        except StartupSchemaError as exc:
            LOGGER.error(safe_startup_event("startup_schema_invalid", explanation=str(exc)))
            raise
        except Exception:
            LOGGER.error(
                safe_startup_event(
                    "startup_database_unavailable",
                    explanation="Application database could not be opened.",
                )
            )
            raise RuntimeError("application database is unavailable") from None
        LOGGER.info(
            safe_startup_event(
                "startup_succeeded", **(getattr(app.state.resources, "startup_details", None) or {})
            )
        )
        try:
            yield
        finally:
            app.state.resources.close()

    app = FastAPI(title="SEC Filing RAG", version="0.2.0", lifespan=lifespan)
    middleware_config = config or SessionSettings()
    session_secret = middleware_config.session_secret
    public_base_url = middleware_config.public_base_url
    secure_cookie = public_base_url.startswith("https://")
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret,
        session_cookie="sec-rag-oauth-state",
        max_age=600,
        same_site="lax",
        https_only=secure_cookie,
    )
    if config is not None:
        app.dependency_overrides[settings] = lambda: config
    install_observability(app)
    app.include_router(public_router)
    app.include_router(internal_router)
    selected_frontend = middleware_config.frontend_dist_path
    if selected_frontend is not None:
        app.mount("/", SPAStaticFiles(directory=selected_frontend, html=True), name="frontend")
    return app


app = create_app()


def run() -> None:
    try:
        config = settings()
    except ValidationError as exc:
        configure_logging("INFO")
        fields = sorted({str(error.get("loc", ("settings",))[0]) for error in exc.errors()})
        LOGGER.error(safe_startup_event("startup_configuration_invalid", fields=fields))
        raise SystemExit(1) from None
    configure_logging(config.log_level)
    uvicorn.run("sec_filing_rag.main:app", host=config.app_host, port=config.app_port)
