from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row


class Database:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    @contextmanager
    def transaction(self):  # type: ignore[no-untyped-def]
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            yield connection


class FilingRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def readiness(self, ticker: str, accessions: list[str]) -> dict[str, dict[str, Any]]:
        if not accessions:
            return {}
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT f.accession,cv.id AS corpus_version_id FROM silver.filing f "
                "JOIN public.company c ON c.id=f.company_id "
                "JOIN silver.corpus_version cv ON cv.filing_id=f.id AND cv.status='ready' "
                "WHERE c.ticker=%s AND f.accession=ANY(%s) "
                "ORDER BY cv.ready_at DESC",
                (ticker, accessions),
            ).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            result.setdefault(
                row["accession"],
                {"ready": True, "corpus_version_id": str(row["corpus_version_id"])},
            )
        return result


class PreparationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        *,
        ticker: str,
        requested_year: int,
        selected_accession: str,
        selected_fiscal_year: int,
        confirmation_required: bool,
    ) -> uuid.UUID:
        request_id = uuid.uuid4()
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT id FROM public.company WHERE ticker=%s AND enabled", (ticker,)
            ).fetchone()
            if row is None:
                raise ValueError("company is unknown or disabled")
            connection.execute(
                "INSERT INTO public.preparation_request"
                "(id,company_id,requested_year,selected_accession,selected_fiscal_year,"
                "confirmation_required,confirmation_state,status) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'pending')",
                (
                    request_id,
                    row["id"],
                    requested_year,
                    selected_accession,
                    selected_fiscal_year,
                    confirmation_required,
                    "confirmed" if confirmation_required else "not_required",
                ),
            )
        return request_id

    def submitted(self, request_id: uuid.UUID, execution_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE public.preparation_request SET status='submitted',"
                "kestra_execution_id=%s,submitted_at=now(),updated_at=now() WHERE id=%s",
                (execution_id, request_id),
            )

    def submission_failed(self, request_id: uuid.UUID, error: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE public.preparation_request SET status='submission_failed',"
                "safe_error=%s,finished_at=now(),updated_at=now() WHERE id=%s",
                (error, request_id),
            )
