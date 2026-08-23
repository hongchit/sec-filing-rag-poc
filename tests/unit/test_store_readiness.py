from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest

from sec_filing_rag.repositories.system import SystemRepository


class Result:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.row = row

    def fetchone(self) -> dict[str, object] | None:
        return self.row


class Connection:
    def __init__(self, relations: dict[str, object], migration: bool) -> None:
        self.relations = relations
        self.migration = migration
        self.queries: list[tuple[str, object]] = []

    def execute(self, query: str, params: object = None) -> Result:
        self.queries.append((query, params))
        if "to_regclass" in query:
            return Result(self.relations)
        return Result({"exists": 1} if self.migration else None)


def store_with(connection: Connection | None) -> SystemRepository:
    class Database:
        @contextmanager
        def transaction(self) -> Iterator[Any]:
            if connection is None:
                raise psycopg.OperationalError("database unavailable")
            yield connection

    return SystemRepository(Database())  # type: ignore[arg-type]


def relations(**missing: None) -> dict[str, object]:
    result: dict[str, object] = {
        "schema_migration": "schema_migration",
        "company": "company",
        "corpus_version": "corpus_version",
        "search_document": "search_document",
    }
    result.update(missing)
    return result


def test_ready_is_false_when_database_is_unavailable() -> None:
    assert store_with(None).ready() is False


def test_ready_is_false_when_migration_record_is_missing() -> None:
    connection = Connection(relations(), migration=False)
    assert store_with(connection).ready() is False
    assert connection.queries[1][1] == ("0001_schema.sql",)


@pytest.mark.parametrize("missing", ["company", "corpus_version", "search_document"])
def test_ready_is_false_when_required_relation_is_missing(missing: str) -> None:
    connection = Connection(relations(**{missing: None}), migration=True)
    assert store_with(connection).ready() is False
    assert len(connection.queries) == 1


def test_ready_is_true_for_initialized_schema() -> None:
    assert store_with(Connection(relations(), migration=True)).ready() is True
