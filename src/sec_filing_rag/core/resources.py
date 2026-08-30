from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import httpx
from openai import OpenAI

from ..domain.filings import sha256_bytes
from ..repositories.corpus import migration_files
from ..repositories.database import Database
from .config import Settings
from .startup import validate_startup_configuration


class StartupSchemaError(RuntimeError):
    pass


def validate_database_schema(database: Database) -> list[str]:
    expected = {path.name: sha256_bytes(path.read_bytes()) for path in migration_files()}
    try:
        with database.transaction() as connection:
            relation = connection.execute(
                "SELECT to_regclass('public.schema_migration') AS value"
            ).fetchone()
            if relation is None or relation["value"] is None:
                raise StartupSchemaError(
                    "application schema is missing; run `uv run sec-rag-migrate`"
                )
            rows = connection.execute(
                "SELECT name,sha256 FROM public.schema_migration ORDER BY name"
            ).fetchall()
            applied = {row["name"]: str(row["sha256"]) for row in rows}
            if any(applied.get(name) != digest for name, digest in expected.items()):
                raise StartupSchemaError(
                    "migrations are pending or checksums differ; run `uv run sec-rag-migrate`"
                )
            required = connection.execute(
                "SELECT to_regclass('public.research_request') AS request,"
                "to_regclass('public.research_result') AS result,to_regclass('public.llm_usage') AS usage"
            ).fetchone()
            if required is None or any(value is None for value in required.values()):
                raise StartupSchemaError(
                    "required application relations are missing; run `uv run sec-rag-migrate`"
                )
        return sorted(expected)
    except StartupSchemaError:
        raise
    except Exception:
        raise StartupSchemaError(
            "database schema validation failed; verify connectivity and migrations"
        ) from None


@dataclass
class AppResources:
    database: Database
    http: httpx.Client
    openai: OpenAI
    startup_details: dict[str, object] | None = None

    def close(self) -> None:
        self.openai.close()
        self.http.close()
        self.database.close()


def create_resources(config: Settings) -> AppResources:
    retrieval, generation, pricing = validate_startup_configuration(config)
    database = Database(
        config.database_url,
        min_size=config.database_pool_min_size,
        max_size=config.database_pool_max_size,
        timeout=config.database_pool_timeout_seconds,
        open=False,
    )
    try:
        database.open(timeout=config.database_startup_timeout_seconds)
        applied_migrations = validate_database_schema(database)
        return AppResources(
            database=database,
            http=httpx.Client(),
            openai=OpenAI(api_key=config.openai_api_key, timeout=config.openai_timeout_seconds),
            startup_details={
                "retrieval_configuration_sha256": retrieval.sha256(),
                "generation_configuration_sha256": generation.sha256(),
                "embedding_model": config.openai_embedding_model,
                "chat_model": config.openai_chat_model,
                "pricing_version": pricing.version,
                "pricing_sha256": pricing.sha256(),
                "applied_migrations": applied_migrations,
            },
        )
    except Exception:
        database.close()
        raise


@contextmanager
def resource_context(config: Settings) -> Iterator[AppResources]:
    resources = create_resources(config)
    try:
        yield resources
    finally:
        resources.close()
