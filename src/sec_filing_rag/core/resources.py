from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import httpx
from openai import OpenAI

from ..repositories.database import Database
from .config import Settings


@dataclass
class AppResources:
    database: Database
    http: httpx.Client
    openai: OpenAI

    def close(self) -> None:
        self.openai.close()
        self.http.close()
        self.database.close()


def create_resources(config: Settings) -> AppResources:
    database = Database(
        config.database_url,
        min_size=config.database_pool_min_size,
        max_size=config.database_pool_max_size,
        timeout=config.database_pool_timeout_seconds,
        open=False,
    )
    database.open(timeout=config.database_startup_timeout_seconds)
    return AppResources(
        database=database,
        http=httpx.Client(),
        openai=OpenAI(api_key=config.openai_api_key, timeout=config.openai_timeout_seconds),
    )


@contextmanager
def resource_context(config: Settings) -> Iterator[AppResources]:
    resources = create_resources(config)
    try:
        yield resources
    finally:
        resources.close()
