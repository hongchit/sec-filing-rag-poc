from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .core.observability import LOGGER

ResearchGoal = Literal[
    "business",
    "key_risks",
    "management_analysis",
    "market_risk",
    "legal_regulatory_risk",
]


class ShowcaseExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,9}$")
    filing_period: str = Field(min_length=1)
    accession: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    items: list[str] = Field(min_length=1)
    citations: list[str] = Field(min_length=1)
    goal: ResearchGoal

    @field_validator("id", "question", "answer", "filing_period")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("items")
    @classmethod
    def valid_items(cls, values: list[str]) -> list[str]:
        allowed = {"1", "1A", "3", "7", "7A", "8"}
        if any(value not in allowed for value in values) or len(set(values)) != len(values):
            raise ValueError("items must be unique supported Form 10-K Items")
        return values

    @field_validator("citations")
    @classmethod
    def valid_citations(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or not re.fullmatch(r"[^\s]{1,240}", value) for value in values):
            raise ValueError("citations must be nonblank handles without whitespace")
        return values


class ShowcaseResponse(BaseModel):
    examples: list[ShowcaseExample]


def load_showcase(path: Path) -> ShowcaseResponse:
    """Load valid editorial examples without making the site depend on showcase content."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        LOGGER.warning('{"event":"showcase_disabled","reason":"configuration_unavailable"}')
        return ShowcaseResponse(examples=[])
    if not isinstance(raw, dict) or raw.get("version") != "showcase-v1":
        LOGGER.warning('{"event":"showcase_disabled","reason":"version_invalid"}')
        return ShowcaseResponse(examples=[])
    candidates = raw.get("examples")
    if not isinstance(candidates, list):
        LOGGER.warning('{"event":"showcase_disabled","reason":"examples_invalid"}')
        return ShowcaseResponse(examples=[])
    examples: list[ShowcaseExample] = []
    seen: set[str] = set()
    for index, candidate in enumerate(candidates):
        try:
            example = ShowcaseExample.model_validate(candidate)
            if example.id in seen:
                raise ValueError("duplicate id")
        except (ValidationError, ValueError):
            LOGGER.warning(
                '{"event":"showcase_entry_skipped","index":%d,"reason":"entry_invalid"}',
                index,
            )
            continue
        seen.add(example.id)
        examples.append(example)
    return ShowcaseResponse(examples=examples)
