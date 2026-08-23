from __future__ import annotations

import psycopg

from .database import Database


class SystemRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def ready(self) -> bool:
        try:
            with self.database.transaction() as connection:
                relations = connection.execute(
                    "SELECT to_regclass('public.schema_migration') AS schema_migration,"
                    "to_regclass('public.company') AS company,"
                    "to_regclass('silver.corpus_version') AS corpus_version,"
                    "to_regclass('gold.search_document') AS search_document"
                ).fetchone()
                if relations is None or any(value is None for value in relations.values()):
                    return False
                migration = connection.execute(
                    "SELECT 1 FROM public.schema_migration WHERE name=%s",
                    ("0001_schema.sql",),
                ).fetchone()
                return migration is not None
        except psycopg.Error:
            return False
