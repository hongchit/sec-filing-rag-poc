from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from ..domain.filings import safe_error
from ..integrations.sec import (
    AcquiredFiling,
    EdgarCompanySnapshot,
    EdgarFilingDocument,
    EdgarFilingMetadata,
)
from .database import Database


class WorkflowRepository:
    """Application-owned state used by both public submission and internal execution APIs."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create_batch(
        self, *, tickers: list[str], fiscal_year: int | None, request_id: str | None
    ) -> tuple[uuid.UUID, list[uuid.UUID]]:
        batch_id = uuid.uuid4()
        item_ids: list[uuid.UUID] = []
        mode = "exact_year" if fiscal_year is not None else "latest"
        # Batch and ordered work items commit together. Kestra is submitted only afterwards.
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT id,ticker FROM public.company WHERE enabled AND ticker=ANY(%s)", (tickers,)
            ).fetchall()
            companies = {row["ticker"]: row["id"] for row in rows}
            missing = [ticker for ticker in tickers if ticker not in companies]
            if missing:
                raise ValueError("unknown or disabled tickers: " + ", ".join(missing))
            connection.execute(
                "INSERT INTO public.filing_batch(id,mode,fiscal_year,request_id) VALUES (%s,%s,%s,%s)",
                (batch_id, mode, fiscal_year, request_id),
            )
            for position, ticker in enumerate(tickers):
                item_id = uuid.uuid4()
                item_ids.append(item_id)
                connection.execute(
                    "INSERT INTO public.filing_batch_item(id,batch_id,company_id,position) "
                    "VALUES (%s,%s,%s,%s)",
                    (item_id, batch_id, companies[ticker], position),
                )
        return batch_id, item_ids

    def submitted(self, batch_id: uuid.UUID, execution_id: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE public.filing_batch SET kestra_execution_id=%s,status='submitted',updated_at=now() "
                "WHERE id=%s",
                (execution_id, batch_id),
            )

    def submission_failed(self, batch_id: uuid.UUID, error: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE public.filing_batch SET status='failed',safe_error=%s,finished_at=now(),updated_at=now() "
                "WHERE id=%s",
                (safe_error(error), batch_id),
            )
            connection.execute(
                "UPDATE public.filing_batch_item SET status='failed',safe_error=%s,finished_at=now(),updated_at=now() "
                "WHERE batch_id=%s AND status='pending'",
                (safe_error(error), batch_id),
            )

    def item_context(self, item_id: uuid.UUID, *, lock: bool = False) -> dict[str, Any]:
        suffix = " FOR UPDATE" if lock else ""
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT bi.id,bi.batch_id,bi.status::text AS status,bi.selected_accession,bi.acquisition_id,"
                "b.mode::text AS mode,b.fiscal_year,b.kestra_execution_id,c.id AS company_id,c.ticker "
                "FROM public.filing_batch_item bi JOIN public.filing_batch b ON b.id=bi.batch_id "
                "JOIN public.company c ON c.id=bi.company_id WHERE bi.id=%s" + suffix,
                (item_id,),
            ).fetchone()
            if row is None:
                raise ValueError("unknown filing batch item")
            return dict(row)

    def transition(
        self,
        item_id: uuid.UUID,
        status: str,
        *,
        accession: str | None = None,
        acquisition_id: uuid.UUID | None = None,
        corpus_version_id: uuid.UUID | None = None,
        error: str | None = None,
        execution_id: str | None = None,
    ) -> None:
        terminal = status in {"succeeded", "skipped", "failed"}
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT batch_id FROM public.filing_batch_item WHERE id=%s FOR UPDATE", (item_id,)
            ).fetchone()
            if row is None:
                raise ValueError("unknown filing batch item")
            connection.execute(
                "UPDATE public.filing_batch_item SET status=%s,"
                "selected_accession=COALESCE(%s,selected_accession),"
                "acquisition_id=COALESCE(%s,acquisition_id),corpus_version_id=COALESCE(%s,corpus_version_id),"
                "safe_error=%s,started_at=COALESCE(started_at,now()),"
                "finished_at=CASE WHEN %s THEN now() ELSE NULL END,updated_at=now() WHERE id=%s",
                (
                    status,
                    accession,
                    acquisition_id,
                    corpus_version_id,
                    safe_error(error) if error else None,
                    terminal,
                    item_id,
                ),
            )
            connection.execute(
                "UPDATE public.filing_batch SET status='running',kestra_execution_id=COALESCE(%s,kestra_execution_id),"
                "updated_at=now() WHERE id=%s AND status='submitted'",
                (execution_id, row["batch_id"]),
            )

    def save_acquisition(self, item_id: uuid.UUID, acquired: AcquiredFiling) -> uuid.UUID:
        context = self.item_context(item_id)
        payload = {
            "company": asdict(acquired.company),
            "filing": asdict(acquired.filing),
            "document": {
                key: value for key, value in asdict(acquired.document).items() if key != "content"
            },
        }
        acquisition_id = uuid.uuid4()
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO bronze.filing_acquisition"
                "(id,company_id,accession,payload,content,media_type,content_sha256,content_length) "
                "VALUES (%s,%s,%s,%s,%s,'text/html',%s,%s) ON CONFLICT "
                "(company_id,accession,content_sha256) DO NOTHING",
                (
                    acquisition_id,
                    context["company_id"],
                    acquired.filing.accession,
                    json.dumps(payload, default=str),
                    acquired.document.content,
                    acquired.document.sha256,
                    len(acquired.document.content),
                ),
            )
            row = connection.execute(
                "SELECT id FROM bronze.filing_acquisition WHERE company_id=%s AND accession=%s "
                "AND content_sha256=%s",
                (context["company_id"], acquired.filing.accession, acquired.document.sha256),
            ).fetchone()
        return uuid.UUID(str(row["id"]))

    def load_acquisition(self, acquisition_id: uuid.UUID) -> AcquiredFiling:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT payload,content FROM bronze.filing_acquisition WHERE id=%s",
                (acquisition_id,),
            ).fetchone()
        if row is None:
            raise ValueError("unknown acquisition")
        payload = row["payload"]
        company = payload["company"]
        company["tickers"] = tuple(company["tickers"])
        company["exchanges"] = tuple(company["exchanges"])
        filing = payload["filing"]
        filing["filing_date"] = date.fromisoformat(filing["filing_date"])
        filing["report_date"] = date.fromisoformat(filing["report_date"])
        if filing["acceptance_datetime"] is not None:
            filing["acceptance_datetime"] = datetime.fromisoformat(filing["acceptance_datetime"])
        return AcquiredFiling(
            EdgarCompanySnapshot(**company),
            EdgarFilingMetadata(**filing),
            EdgarFilingDocument(**payload["document"], content=bytes(row["content"])),
        )

    def batch(self, batch_id: uuid.UUID) -> dict[str, Any] | None:
        with self.database.transaction() as connection:
            batch = connection.execute(
                "SELECT id AS batch_id,mode::text AS mode,fiscal_year,status::text AS status,request_id,"
                "kestra_execution_id,created_at,updated_at FROM public.filing_batch WHERE id=%s",
                (batch_id,),
            ).fetchone()
            if batch is None:
                return None
            items = connection.execute(
                "SELECT bi.id,bi.position,c.ticker,bi.status::text AS status,bi.selected_accession,"
                "bi.acquisition_id,bi.corpus_version_id,bi.safe_error,bi.started_at,bi.finished_at "
                "FROM public.filing_batch_item bi JOIN public.company c ON c.id=bi.company_id "
                "WHERE bi.batch_id=%s ORDER BY bi.position",
                (batch_id,),
            ).fetchall()
        return {**dict(batch), "items": [dict(item) for item in items]}

    def finalize(self, batch_id: uuid.UUID, execution_id: str | None = None) -> str:
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT status::text AS status,count(*)::integer AS count FROM public.filing_batch_item "
                "WHERE batch_id=%s GROUP BY status",
                (batch_id,),
            ).fetchall()
            counts = {row["status"]: row["count"] for row in rows}
            success = counts.get("succeeded", 0)
            incomplete = sum(
                counts.get(value, 0)
                for value in ("pending", "selecting", "acquiring", "processing")
            )
            if incomplete:
                connection.execute(
                    "UPDATE public.filing_batch_item SET status='failed',safe_error='workflow ended before item completion',"
                    "finished_at=now(),updated_at=now() WHERE batch_id=%s AND status IN "
                    "('pending','selecting','acquiring','processing')",
                    (batch_id,),
                )
            total = sum(counts.values())
            non_success = total - success
            status = "failed" if success == 0 else "partial_failure" if non_success else "succeeded"
            connection.execute(
                "UPDATE public.filing_batch SET status=%s,kestra_execution_id=COALESCE(%s,kestra_execution_id),"
                "finished_at=now(),updated_at=now() WHERE id=%s",
                (status, execution_id, batch_id),
            )
        return status
