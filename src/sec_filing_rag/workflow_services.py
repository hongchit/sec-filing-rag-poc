from __future__ import annotations

import uuid

from .config import Settings, load_companies
from .domain import safe_error
from .errors import UpstreamServiceError
from .kestra import KestraGateway
from .pipeline import IngestionPipeline
from .sec import EdgarGateway
from .store import Store
from .workflow_repository import WorkflowRepository


class FilingBatchService:
    def __init__(
        self, settings: Settings, repository: WorkflowRepository, kestra: KestraGateway, store: Store
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.kestra = kestra
        self.store = store

    def submit(
        self, *, tickers: list[str] | None, fiscal_year: int | None, request_id: str | None
    ) -> tuple[uuid.UUID, str, list[str]]:
        configuration = load_companies(self.settings.company_config_path)
        self.store.load_configuration(configuration, self.settings.company_config_path)
        configured = configuration.companies
        enabled = [entry.ticker for entry in configured if entry.enabled]
        selected = enabled if tickers is None else tickers
        if not selected:
            raise ValueError("company configuration has no enabled tickers")
        unavailable = [ticker for ticker in selected if ticker not in enabled]
        if unavailable:
            raise ValueError("unknown or disabled tickers: " + ", ".join(unavailable))
        batch_id, _ = self.repository.create_batch(
            tickers=selected, fiscal_year=fiscal_year, request_id=request_id
        )
        try:
            execution = self.kestra.submit_batch(batch_id=str(batch_id))
        except Exception as exc:
            error = safe_error(exc, (self.settings.kestra_basic_auth_password,))
            self.repository.submission_failed(batch_id, error)
            raise UpstreamServiceError(
                error, public_detail="workflow submission failed", code="kestra_submission_failure"
            ) from exc
        self.repository.submitted(batch_id, execution.id)
        return batch_id, execution.id, selected


class FilingExecutionService:
    def __init__(
        self,
        settings: Settings,
        repository: WorkflowRepository,
        provider: EdgarGateway,
        pipeline: IngestionPipeline,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.provider = provider
        self.pipeline = pipeline

    def select(self, item_id: uuid.UUID, execution_id: str | None) -> tuple[str | None, int | None]:
        context = self.repository.item_context(item_id)
        if context["status"] in {"skipped", "succeeded"}:
            return context["selected_accession"], context["fiscal_year"]
        self.repository.transition(item_id, "selecting", execution_id=execution_id)
        _, _, candidates = self.provider.discover_candidates(context["ticker"])
        if context["mode"] == "latest":
            selected = max(
                (candidate for candidate in candidates if candidate.report_date is not None),
                key=lambda candidate: (candidate.report_date, candidate.filing_date, candidate.accession),
            )
        else:
            exact = [candidate for candidate in candidates if candidate.fiscal_year == context["fiscal_year"]]
            if not exact:
                self.repository.transition(
                    item_id, "skipped", error=f"no original 10-K for fiscal year {context['fiscal_year']}"
                )
                return None, context["fiscal_year"]
            selected = max(exact, key=lambda candidate: (candidate.filing_date, candidate.accession))
        self.repository.transition(item_id, "acquiring", accession=selected.accession)
        return selected.accession, selected.fiscal_year

    def acquire(self, item_id: uuid.UUID, execution_id: str | None) -> tuple[uuid.UUID, str, str, int]:
        context = self.repository.item_context(item_id)
        if context["selected_accession"] is None:
            raise ValueError("filing item has no selected accession")
        if context["acquisition_id"] is not None:
            acquired = self.repository.load_acquisition(context["acquisition_id"])
            return (
                context["acquisition_id"],
                acquired.filing.accession,
                acquired.document.sha256,
                len(acquired.document.content),
            )
        self.repository.transition(item_id, "acquiring", execution_id=execution_id)
        acquired = self.provider.acquire(
            context["ticker"],
            accession=context["selected_accession"],
            max_bytes=self.settings.max_filing_document_bytes,
        )
        acquisition_id = self.repository.save_acquisition(item_id, acquired)
        self.repository.transition(item_id, "processing", acquisition_id=acquisition_id)
        return (
            acquisition_id,
            acquired.filing.accession,
            acquired.document.sha256,
            len(acquired.document.content),
        )

    def process(
        self, item_id: uuid.UUID, execution_id: str | None
    ) -> tuple[str, uuid.UUID | None, bool, str | None]:
        context = self.repository.item_context(item_id)
        if context["status"] == "succeeded":
            batch = self.repository.batch(context["batch_id"])
            item = next(entry for entry in batch["items"] if entry["id"] == item_id)  # type: ignore[index]
            return "succeeded", item["corpus_version_id"], context["mode"] == "latest", None
        if context["acquisition_id"] is None:
            raise ValueError("filing item has no acquisition")
        self.repository.transition(item_id, "processing", execution_id=execution_id)
        acquired = self.repository.load_acquisition(context["acquisition_id"])
        result = self.pipeline.run_company(
            context["ticker"],
            "historical" if context["mode"] == "exact_year" else "api",
            selected_accession=acquired.filing.accession,
            kestra_execution_id=execution_id,
            acquired_filing=acquired,
            promote_default=context["mode"] == "latest",
        )
        if result.outcome == "failed":
            self.repository.transition(item_id, "failed", error=result.error)
            return "failed", None, False, result.error
        ready = self.pipeline.store.ready_corpus(
            self.repository.item_context(item_id)["company_id"],
            acquired.filing.accession,
            self.pipeline.store.run_compatibility_key(result.run_id),
        )
        corpus_id = ready["corpus_version_id"] if ready else None
        final = "skipped" if result.outcome == "skipped" else "succeeded"
        self.repository.transition(item_id, final, corpus_version_id=corpus_id)
        return final, corpus_id, context["mode"] == "latest" and final == "succeeded", None
