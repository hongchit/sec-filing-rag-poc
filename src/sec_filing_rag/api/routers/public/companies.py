from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ....core.config import TICKER_RE, load_companies
from ....repositories.companies import CompanyRepository
from ....schemas.companies import CompanyStatus, CompanySummary
from ...dependencies import company_repository, settings

router = APIRouter()


@router.get(
    "/companies",
    response_model=list[CompanySummary],
    tags=["companies"],
    operation_id="listCompanies",
    description="List configured companies and corpus readiness.",
)
def companies(repository: Annotated[CompanyRepository, Depends(company_repository)]) -> list[CompanySummary]:
    configured = load_companies(settings().company_config_path).companies
    stored = {entry["ticker"]: entry for entry in repository.list()}
    return [
        CompanySummary.model_validate(
            {
                **stored.get(entry.ticker, {"ticker": entry.ticker, "resolution_status": "pending"}),
                "enabled": entry.enabled,
            }
        )
        for entry in configured
    ]


@router.get(
    "/companies/{ticker}/status",
    response_model=CompanyStatus,
    tags=["companies"],
    operation_id="getCompanyStatus",
    description="Inspect application-owned corpus status without querying Kestra.",
)
def company_status(
    ticker: str, repository: Annotated[CompanyRepository, Depends(company_repository)]
) -> CompanyStatus:
    normalized = ticker.strip().upper()
    if not TICKER_RE.fullmatch(normalized):
        raise HTTPException(status_code=422, detail="invalid ticker")
    configured = {entry.ticker: entry for entry in load_companies(settings().company_config_path).companies}
    if normalized not in configured:
        raise HTTPException(status_code=404, detail="unknown configured ticker")
    result = repository.status(normalized) or {
        "ticker": normalized,
        "active_corpus": None,
        "coverage": [],
        "latest_run": None,
    }
    return CompanyStatus.model_validate({**result, "enabled": configured[normalized].enabled})
