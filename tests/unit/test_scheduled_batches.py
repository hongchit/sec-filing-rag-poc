from __future__ import annotations

import uuid

import pytest

from sec_filing_rag.core.config import Settings
from sec_filing_rag.services.workflows import ScheduledFilingBatchService


class Creator:
    def __init__(self) -> None:
        self.arguments = None

    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        self.arguments = kwargs
        return uuid.UUID(int=4), ["AAPL"], True


class Auth:
    def __init__(self, owner_id: uuid.UUID | None) -> None:
        self.owner_id = owner_id

    def active_user_id_by_email(self, email: str) -> uuid.UUID | None:
        assert email == "first@example.com"
        return self.owner_id


def settings() -> Settings:
    return Settings(
        ingestion_api_token="0123456789abcdef",
        edgar_identity="Test test@example.com",
        openai_api_key="key",
        google_admin_emails="first@example.com,second@example.com",
    )


def test_scheduled_batch_is_owned_by_first_configured_active_admin() -> None:
    owner_id = uuid.uuid4()
    creator = Creator()
    service = ScheduledFilingBatchService(settings(), creator, Auth(owner_id))  # type: ignore[arg-type]

    batch_id, tickers = service.create(
        tickers=None,
        fiscal_year=None,
        request_id="request-1",
        launcher_execution_id="execution-1",
    )

    assert batch_id == uuid.UUID(int=4) and tickers == ["AAPL"]
    assert creator.arguments["user_id"] == owner_id
    assert creator.arguments["launcher_execution_id"] == "execution-1"


def test_scheduled_batch_fails_before_creation_without_active_primary_admin() -> None:
    creator = Creator()
    service = ScheduledFilingBatchService(settings(), creator, Auth(None))  # type: ignore[arg-type]

    with pytest.raises(LookupError, match="has not signed in"):
        service.create(
            tickers=None,
            fiscal_year=None,
            request_id="request-1",
            launcher_execution_id="execution-1",
        )

    assert creator.arguments is None
