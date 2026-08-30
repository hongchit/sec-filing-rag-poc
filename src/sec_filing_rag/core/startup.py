from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..generation.service import load_generation_configuration
from ..retrieval.service import load_retrieval_configuration
from .config import Settings, load_companies
from .pricing import PricingConfiguration, load_pricing_configuration


@dataclass(frozen=True)
class StartupIssue:
    code: str
    category: str
    explanation: str
    remediation: str


class StartupConfigurationError(RuntimeError):
    def __init__(self, issues: list[StartupIssue]) -> None:
        self.issues = issues
        super().__init__("startup configuration is invalid; inspect startup_configuration_invalid")


PLACEHOLDERS = {
    "change-me",
    "changeme1234",
    "change-me-at-least-16-characters",
    "__required__",
    "your-email@example.com",
    "admin@example.com",
    "key",
}


def _placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        not normalized
        or normalized in PLACEHOLDERS
        or "change-me" in normalized
        or "__required__" in normalized
        or "your-email@example.com" in normalized
    )


def validate_startup_configuration(config: Settings) -> tuple[Any, Any, PricingConfiguration]:
    issues: list[StartupIssue] = []

    def issue(code: str, category: str, explanation: str, remediation: str) -> None:
        issues.append(StartupIssue(code, category, explanation, remediation))

    secret_fields = (
        "openai_api_key",
        "ingestion_api_token",
        "kestra_basic_auth_username",
        "kestra_basic_auth_password",
        "database_url",
        "google_client_id",
        "google_client_secret",
        "session_secret",
        "google_admin_emails",
    )
    for field in secret_fields:
        if _placeholder(str(getattr(config, field))):
            issue(
                "placeholder_value",
                field,
                "A required setting is missing or uses a known placeholder.",
                f"Set {field.upper()} to a non-placeholder value.",
            )

    loaded: dict[str, Any] = {}
    loaders = {
        "companies": (config.company_config_path, load_companies),
        "retrieval": (config.retrieval_config_path, load_retrieval_configuration),
        "generation": (config.generation_config_path, load_generation_configuration),
        "model_pricing": (config.model_pricing_config_path, load_pricing_configuration),
    }
    for category, (path, loader) in loaders.items():
        try:
            loaded[category] = loader(path)
        except Exception:
            issue(
                "configuration_file_invalid",
                category,
                "The tracked configuration file is missing, unreadable, or invalid.",
                f"Correct the tracked {category} configuration file.",
            )

    companies = loaded.get("companies")
    if companies is not None and not any(company.enabled for company in companies.companies):
        issue(
            "no_enabled_companies",
            "companies",
            "At least one uniquely named company must be enabled.",
            "Enable at least one company ticker.",
        )
    retrieval = loaded.get("retrieval")
    if retrieval is not None:
        if retrieval.default is None:
            issue(
                "retrieval_default_missing",
                "retrieval",
                "A promoted retrieval default is required.",
                "Select a default from the validated retrieval grid.",
            )
        if (
            retrieval.embedding_model != config.openai_embedding_model
            or retrieval.embedding_dimensions != config.openai_embedding_dimensions
        ):
            issue(
                "embedding_configuration_mismatch",
                "retrieval",
                "Retrieval and runtime embedding settings differ.",
                "Align the exact embedding model and dimensions.",
            )
    generation = loaded.get("generation")
    if generation is not None:
        if generation.promoted_prompt_id is None:
            issue(
                "promoted_prompt_missing",
                "generation",
                "A promoted generation prompt is required.",
                "Set promoted_prompt_id to a configured prompt.",
            )
        for prompt in generation.prompts:
            try:
                generation.prompt(prompt.id)
            except Exception:
                issue(
                    "prompt_file_invalid",
                    "generation",
                    "A referenced prompt is missing or unreadable.",
                    "Restore every referenced prompt file.",
                )
    pricing = loaded.get("model_pricing")
    if pricing is not None:
        embedding_price = pricing.models.get(config.openai_embedding_model)
        chat_price = pricing.models.get(config.openai_chat_model)
        if embedding_price is None:
            issue(
                "embedding_price_missing",
                "model_pricing",
                "The active embedding model has no input price.",
                "Add an exact model pricing entry.",
            )
        if chat_price is None or chat_price.output_usd_per_million_tokens is None:
            issue(
                "generation_price_missing",
                "model_pricing",
                "The active generation model requires input and output prices.",
                "Add both rates for the exact chat model.",
            )
    if issues:
        raise StartupConfigurationError(issues)
    assert pricing is not None
    return retrieval, generation, pricing


def safe_startup_event(event: str, **fields: Any) -> str:
    return json.dumps({"event": event, **fields}, separators=(",", ":"), default=str)
