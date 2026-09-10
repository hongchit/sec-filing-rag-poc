from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any

from sec_filing_rag.repositories.workflows import WorkflowRepository


class Cursor:
    def __init__(
        self, *, row: dict[str, Any] | None = None, rows: list[dict[str, Any]] | None = None
    ):
        self.row = row
        self.rows = rows or []

    def fetchone(self) -> dict[str, Any] | None:
        return self.row

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, statement: str, params: tuple[Any, ...]) -> Cursor:
        self.calls.append((statement, params))
        if statement.startswith("SELECT id,status::text AS status"):
            return Cursor(
                row={
                    "id": uuid.UUID(int=2),
                    "status": "reserved",
                    "reserved_usd": "0.05",
                    "pricing_snapshot": {},
                }
            )
        return Cursor(rows=[])


class Database:
    def __init__(self) -> None:
        self.connection = Connection()

    @contextmanager
    def transaction(self):  # type: ignore[no-untyped-def]
        yield self.connection


def test_submission_failure_releases_reservation_when_no_model_usage_exists() -> None:
    database = Database()
    repository = WorkflowRepository(database)  # type: ignore[arg-type]

    repository.submission_failed(
        uuid.UUID(int=1), "Kestra authentication failed", release_reservation=True
    )

    statements = [statement for statement, _ in database.connection.calls]
    assert any("UPDATE public.filing_batch SET status='failed'" in value for value in statements)
    assert any(
        "UPDATE public.filing_batch_item SET status='failed'" in value for value in statements
    )
    assert any("SET status='reconciled',charged_usd=0" in value for value in statements)


def test_ambiguous_submission_failure_preserves_reservation_for_review() -> None:
    database = Database()
    repository = WorkflowRepository(database)  # type: ignore[arg-type]

    repository.submission_failed(
        uuid.UUID(int=1), "Kestra response timed out", release_reservation=False
    )

    statements = [statement for statement, _ in database.connection.calls]
    assert not any("UPDATE public.cost_action" in value for value in statements)
