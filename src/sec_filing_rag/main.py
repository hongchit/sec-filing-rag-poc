from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from .api.dependencies import settings
from .api.routers.internal import router as internal_router
from .api.routers.public import router as public_router
from .core.config import Settings
from .core.observability import configure_logging, install_observability
from .core.resources import AppResources, create_resources

ResourceFactory = Callable[[Settings], AppResources]


def create_app(
    config: Settings | None = None, *, resource_factory: ResourceFactory = create_resources
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        selected = config or settings()
        configure_logging(selected.log_level)
        app.state.resources = resource_factory(selected)
        try:
            yield
        finally:
            app.state.resources.close()

    app = FastAPI(title="SEC Filing RAG", version="0.2.0", lifespan=lifespan)
    if config is not None:
        app.dependency_overrides[settings] = lambda: config
    install_observability(app)
    app.include_router(public_router)
    app.include_router(internal_router)
    return app


app = create_app()


def run() -> None:
    config = settings()
    configure_logging(config.log_level)
    uvicorn.run("sec_filing_rag.main:app", host=config.app_host, port=config.app_port)
