from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest

from sec_filing_rag.auth import QuotaExceeded, budget_summary, reserve_cost
from sec_filing_rag.core.config import Settings


class Cursor:
    def __init__(self, row: dict[str, Any]) -> None:
        self.row = row

    def fetchone(self) -> dict[str, Any]:
        return self.row


class BudgetConnection:
    def __init__(self, *, override: str | None, used: str, reserved: str) -> None:
        self.override, self.used, self.reserved = override, used, reserved

    def execute(self, statement: str, params: tuple[Any, ...]) -> Cursor:
        del params
        if "lifetime_budget_override_usd" in statement:
            return Cursor({"lifetime_budget_override_usd": self.override})
        return Cursor({"used": self.used, "reserved": self.reserved})


def test_budget_uses_override_and_counts_active_reservations() -> None:
    connection = BudgetConnection(override="2.50", used="1.25", reserved="0.50")
    summary = budget_summary(connection, uuid.uuid4(), Decimal("10"))
    assert summary == {
        "limit_usd": "2.50",
        "used_usd": "1.25",
        "reserved_usd": "0.50",
        "remaining_usd": "1.25",
    }


def test_reservation_fails_closed_at_the_allowance_boundary() -> None:
    connection = BudgetConnection(override=None, used="0.95", reserved="0.10")
    with pytest.raises(QuotaExceeded) as raised:
        reserve_cost(connection, uuid.uuid4(), Decimal("1.00"), Decimal("0.10"))
    assert raised.value.summary["remaining_usd"] == "0.05"


def test_admin_email_configuration_is_normalized() -> None:
    config = Settings(
        ingestion_api_token="0123456789abcdef",
        edgar_identity="Test test@example.com",
        openai_api_key="key",
        google_admin_emails=" Admin@Example.com,second@example.com ",
    )
    assert config.admin_emails == frozenset({"admin@example.com", "second@example.com"})
