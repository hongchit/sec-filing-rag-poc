from __future__ import annotations

import pytest
from pydantic import ValidationError

from sec_filing_rag.core.config import SessionSettings


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({}, ""),
        ({"vite_ga4_measurement_id": " G-TEST123456 "}, "ga4:G-TEST123456"),
        ({"vite_gtm_container_id": "GTM-TEST123"}, "gtm:GTM-TEST123"),
    ],
)
def test_analytics_configuration(values: dict[str, str], expected: str) -> None:
    assert SessionSettings(_env_file=None, **values).analytics_meta_value == expected


@pytest.mark.parametrize(
    "values",
    [
        {"vite_ga4_measurement_id": "not-an-id"},
        {"vite_gtm_container_id": "not-an-id"},
        {
            "vite_ga4_measurement_id": "G-TEST123456",
            "vite_gtm_container_id": "GTM-TEST123",
        },
    ],
)
def test_invalid_analytics_configuration_is_rejected(values: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        SessionSettings(_env_file=None, **values)
