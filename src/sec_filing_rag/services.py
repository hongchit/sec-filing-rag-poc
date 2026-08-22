from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .domain import (
    AnalysisPeriod,
    FilingCandidate,
    FilingSelection,
    confirmed_candidate,
    safe_error,
    select_fiscal_year,
)
from .errors import UpstreamServiceError
from .kestra import KestraGateway
from .repositories import FilingRepository, PreparationRepository


class FilingDiscoveryGateway(Protocol):
    def discover_candidates(self, ticker: str) -> tuple[str, str, list[FilingCandidate]]: ...


@dataclass(frozen=True)
class Discovery:
    ticker: str
    selection: FilingSelection
    readiness: dict[str, dict[str, Any]]

    def candidate(self, value: FilingCandidate | None) -> dict[str, Any] | None:
        if value is None or value.report_date is None:
            return None
        ready = self.readiness.get(value.accession, {})
        return {
            "accession": value.accession,
            "fiscal_year": value.report_date.year,
            "report_date": value.report_date,
            "filing_date": value.filing_date,
            "ready": bool(ready.get("ready", False)),
            "corpus_version_id": ready.get("corpus_version_id"),
        }

    def response(self) -> dict[str, Any]:
        selection = self.selection
        return {
            "ticker": self.ticker,
            "requested_period": {
                "granularity": selection.requested.granularity,
                "value": str(selection.requested.value),
            },
            "lookback": {
                "earliest_year": selection.lookback.earliest_year,
                "latest_year": selection.lookback.latest_year,
            },
            "exact": self.candidate(selection.exact),
            "earlier": self.candidate(selection.earlier),
            "later": self.candidate(selection.later),
        }


class FilingDiscoveryService:
    def __init__(
        self, gateway: FilingDiscoveryGateway, filings: FilingRepository, lookback_years: int
    ) -> None:
        self.gateway = gateway
        self.filings = filings
        self.lookback_years = lookback_years

    def discover(self, ticker: str, period: AnalysisPeriod) -> Discovery:
        _, _, candidates = self.gateway.discover_candidates(ticker)
        selection = select_fiscal_year(candidates, period, self.lookback_years)
        readiness = self.filings.readiness(ticker, [candidate.accession for candidate in candidates])
        return Discovery(ticker, selection, readiness)


class HistoricalPreparationService:
    def __init__(
        self,
        discovery: FilingDiscoveryService,
        requests: PreparationRepository,
        kestra: KestraGateway,
    ) -> None:
        self.discovery = discovery
        self.requests = requests
        self.kestra = kestra

    def submit(self, ticker: str, period: AnalysisPeriod, confirmed_accession: str | None) -> tuple[str, str]:
        discovery = self.discovery.discover(ticker, period)
        selected = confirmed_candidate(discovery.selection, confirmed_accession)
        assert selected.fiscal_year is not None
        confirmation_required = discovery.selection.exact is None
        request_id = self.requests.create(
            ticker=ticker,
            requested_year=period.value,
            selected_accession=selected.accession,
            selected_fiscal_year=selected.fiscal_year,
            confirmation_required=confirmation_required,
        )
        try:
            execution = self.kestra.submit_historical(
                request_id=str(request_id),
                ticker=ticker,
                requested_year=period.value,
                accession=selected.accession,
            )
        except Exception as exc:
            error = safe_error(exc)
            self.requests.submission_failed(request_id, error)
            raise UpstreamServiceError(error, public_detail=error, code="kestra_submission_failure") from exc
        self.requests.submitted(request_id, execution.id)
        return str(request_id), execution.id
