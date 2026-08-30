from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_usd_per_million_tokens: Decimal = Field(ge=0)
    output_usd_per_million_tokens: Decimal | None = Field(default=None, ge=0)

    @field_validator("input_usd_per_million_tokens", "output_usd_per_million_tokens")
    @classmethod
    def finite(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("price must be finite")
        return value


class PricingConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1, max_length=100)
    currency: Literal["USD"]
    token_unit: Literal[1_000_000]
    models: dict[str, ModelPrice]

    def sha256(self) -> str:
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def snapshot(self, *, embedding_model: str, chat_model: str) -> dict[str, Any]:
        embedding = self.models[embedding_model]
        chat = self.models[chat_model]
        if chat.output_usd_per_million_tokens is None:
            raise ValueError("generation model output price is required")
        return {
            "version": self.version,
            "sha256": self.sha256(),
            "currency": self.currency,
            "token_unit": self.token_unit,
            "models": {
                embedding_model: embedding.model_dump(mode="json"),
                chat_model: chat.model_dump(mode="json"),
            },
            "embedding_model": embedding_model,
            "chat_model": chat_model,
        }

    def snapshot_models(self, *models: str) -> dict[str, Any]:
        """Capture the configured rates needed by an operational execution."""
        selected = {model: self.models[model].model_dump(mode="json") for model in models}
        return {
            "version": self.version,
            "sha256": self.sha256(),
            "currency": self.currency,
            "token_unit": self.token_unit,
            "models": selected,
        }


def load_pricing_configuration(path: Path) -> PricingConfiguration:
    return PricingConfiguration.model_validate_json(path.read_text(encoding="utf-8"))


def estimate_charge(
    snapshot: dict[str, Any] | None, operations: list[dict[str, Any]]
) -> tuple[str, str | None]:
    """Return (availability, decimal USD). A missing usage component invalidates the whole estimate."""
    if snapshot is None:
        return "unavailable", None
    try:
        unit = Decimal(str(snapshot["token_unit"]))
        prices = snapshot["models"]
        total = Decimal(0)
        for operation in operations:
            model_price = prices[operation["model"]]
            input_tokens = operation.get("input_tokens")
            if input_tokens is None:
                return "unavailable", None
            total += (
                Decimal(input_tokens)
                * Decimal(str(model_price["input_usd_per_million_tokens"]))
                / unit
            )
            if model_price.get("output_usd_per_million_tokens") is not None:
                output_tokens = operation.get("output_tokens")
                output_rate = model_price.get("output_usd_per_million_tokens")
                if output_tokens is None:
                    return "unavailable", None
                total += Decimal(output_tokens) * Decimal(str(output_rate)) / unit
        if not total.is_finite() or math.isinf(float(total)):
            return "unavailable", None
        return "available", format(total, "f")
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return "unavailable", None
