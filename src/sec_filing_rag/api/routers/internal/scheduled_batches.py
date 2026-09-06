from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from ....auth import QuotaExceeded
from ....schemas.workflows import FilingBatchRequest, ScheduledFilingBatchCreated
from ....services.workflows import ScheduledFilingBatchService
from ...dependencies import scheduled_batch_service

router = APIRouter()


@router.post(
    "/scheduled-filing-batches",
    response_model=ScheduledFilingBatchCreated,
    status_code=status.HTTP_201_CREATED,
    tags=["internal-scheduled-ingestion"],
    operation_id="createScheduledFilingBatch",
    description="Persist an idempotent scheduler-owned batch for the shared Kestra processing flow.",
)
def create_scheduled_batch(
    payload: FilingBatchRequest,
    request: Request,
    launcher_execution_id: Annotated[
        str,
        Header(
            alias="X-Kestra-Execution-ID",
            min_length=1,
            max_length=128,
            pattern=r"^[A-Za-z0-9._:-]+$",
        ),
    ],
    service: Annotated[ScheduledFilingBatchService, Depends(scheduled_batch_service)],
) -> ScheduledFilingBatchCreated:
    try:
        batch_id, tickers = service.create(
            tickers=payload.tickers,
            fiscal_year=payload.fiscal_year,
            request_id=request.state.request_id,
            launcher_execution_id=launcher_execution_id,
        )
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "scheduled_ingestion_owner_unavailable",
                "message": "The first configured administrator must sign in and remain active.",
            },
        ) from None
    except QuotaExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "quota_exceeded", "budget": exc.summary},
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return ScheduledFilingBatchCreated(
        batch_id=batch_id,
        mode="exact_year" if payload.fiscal_year is not None else "latest",
        fiscal_year=payload.fiscal_year,
        tickers=tickers,
    )
