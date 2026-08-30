from decimal import Decimal

from sec_filing_rag.core.pricing import estimate_charge


def snapshot() -> dict[str, object]:
    return {
        "version": "test",
        "sha256": "a" * 64,
        "currency": "USD",
        "token_unit": 1_000_000,
        "models": {
            "embedding": {"input_usd_per_million_tokens": "0.02"},
            "chat": {
                "input_usd_per_million_tokens": "1.00",
                "output_usd_per_million_tokens": "4.00",
            },
        },
    }


def test_any_output_priced_model_charges_input_and_output_tokens() -> None:
    status, charge = estimate_charge(
        snapshot(),
        [
            {
                "operation": "ground_truth_generation",
                "model": "chat",
                "input_tokens": 1_000,
                "output_tokens": 500,
            },
            {
                "operation": "embedding",
                "model": "embedding",
                "input_tokens": 2_000,
                "output_tokens": None,
            },
        ],
    )

    assert status == "available"
    assert Decimal(charge or "0") == Decimal("0.00304")


def test_unknown_model_or_missing_required_usage_is_unavailable() -> None:
    unknown = estimate_charge(
        snapshot(),
        [{"operation": "judge", "model": "unknown", "input_tokens": 1, "output_tokens": 1}],
    )
    missing = estimate_charge(
        snapshot(),
        [{"operation": "judge", "model": "chat", "input_tokens": 1, "output_tokens": None}],
    )

    assert unknown == ("unavailable", None)
    assert missing == ("unavailable", None)
