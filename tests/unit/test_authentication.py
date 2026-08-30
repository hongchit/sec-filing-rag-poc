from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from sec_filing_rag.api.routers.public import authentication
from sec_filing_rag.core.config import Settings


class GoogleClient:
    async def authorize_access_token(self, request: Request) -> dict[str, Any]:
        del request
        return {
            "userinfo": {
                "iss": "https://accounts.google.com",
                "sub": "subject",
                "email": "user@example.com",
                "email_verified": True,
                "name": "Example User",
            }
        }


class OAuthClient:
    google = GoogleClient()


class Repository:
    def __init__(self) -> None:
        self.metadata: dict[str, bool] | None = None

    def upsert_google_user(self, **values: str) -> dict[str, Any]:
        del values
        return {"id": uuid.UUID(int=1), "status": "active"}

    def create_session(self, user_id: uuid.UUID, lifetime_days: int) -> tuple[str, str]:
        del user_id, lifetime_days
        return "session", "csrf"

    def audit(self, event_type: str, outcome: str, **values: Any) -> None:
        assert (event_type, outcome) == ("login", "succeeded")
        self.metadata = values["metadata"]


def request(session: dict[str, Any]) -> Request:
    value = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    value.scope["session"] = session
    return value


def config() -> Settings:
    return Settings(
        ingestion_api_token="0123456789abcdef",
        edgar_identity="Test test@example.com",
        openai_api_key="key",
    )


def test_callback_requires_policy_acknowledgement() -> None:
    with pytest.raises(HTTPException) as raised:
        asyncio.run(authentication.google_callback(request({}), Repository(), config()))  # type: ignore[arg-type]
    assert raised.value.status_code == 400


def test_successful_login_audits_policy_acknowledgements(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(authentication, "_oauth", lambda value: OAuthClient())
    repository = Repository()
    response = asyncio.run(
        authentication.google_callback(
            request({"policy_acknowledged": True, "return_to": "/research"}),
            repository,  # type: ignore[arg-type]
            config(),
        )
    )
    assert response.status_code == 303
    assert repository.metadata == {
        "terms_accepted": True,
        "privacy_notice_acknowledged": True,
        "cookie_notice_acknowledged": True,
    }
