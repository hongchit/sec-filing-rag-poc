from __future__ import annotations

from typing import Any

from .database import Database


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
                "WHERE c.ticker=%s AND f.accession=ANY(%s) ORDER BY cv.ready_at DESC",
                (ticker, accessions),
            ).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            result.setdefault(
                row["accession"],
                {"ready": True, "corpus_version_id": str(row["corpus_version_id"])},
            )
        return result
