#!/usr/bin/env python3
"""Derive Kubernetes env files from literal raw production credentials, offline."""

import argparse
import base64
import math
import os
import re
import sys
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

SECRET_FIELDS = (
    "EDGAR_IDENTITY",
    "OPENAI_API_KEY",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_ADMIN_EMAILS",
    "SESSION_SECRET",
    "INGESTION_API_TOKEN",
    "POSTGRES_PASSWORD",
    "APP_DATABASE_PASSWORD",
    "KESTRA_DATABASE_PASSWORD",
    "KESTRA_BASIC_AUTH_USERNAME",
    "KESTRA_BASIC_AUTH_PASSWORD",
)
OPERATOR_FIELDS = (
    "DATABASE_POOL_MIN_SIZE",
    "DATABASE_POOL_MAX_SIZE",
    "DATABASE_POOL_TIMEOUT_SECONDS",
    "DATABASE_STARTUP_TIMEOUT_SECONDS",
    "LOG_LEVEL",
    "EDGAR_RATE_LIMIT_PER_SEC",
    "EDGAR_ACCESS_MODE",
    "MAX_FILING_DOCUMENT_BYTES",
    "MAX_FILING_NARRATIVE_CHARS",
    "KESTRA_TIMEOUT_SECONDS",
    "KESTRA_MAX_RETRIES",
    "OPENAI_EMBEDDING_MODEL",
    "OPENAI_EMBEDDING_DIMENSIONS",
    "OPENAI_CHAT_MODEL",
    "OPENAI_JUDGE_MODEL",
    "OPENAI_TIMEOUT_SECONDS",
    "CHUNK_SIZE_CHARS",
    "CHUNK_OVERLAP_CHARS",
    "PARSER_VERSION",
    "CHUNKING_VERSION",
    "INDEX_VERSION",
    "SESSION_LIFETIME_DAYS",
    "DEFAULT_USER_LIFETIME_BUDGET_USD",
    "RESEARCH_COST_RESERVATION_USD",
    "CORPUS_PREPARATION_COST_RESERVATION_USD",
)
FIELDS = SECRET_FIELDS + OPERATOR_FIELDS
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
YAML_PLAIN_WORDS = {"true", "false", "null", "yes", "no", "on", "off"}
INTEGER_RANGES = {
    "DATABASE_POOL_MIN_SIZE": (1, None),
    "DATABASE_POOL_MAX_SIZE": (1, None),
    "EDGAR_RATE_LIMIT_PER_SEC": (1, 10),
    "MAX_FILING_DOCUMENT_BYTES": (1_000_000, 100_000_000),
    "MAX_FILING_NARRATIVE_CHARS": (500_000, 50_000_000),
    "KESTRA_MAX_RETRIES": (0, 5),
    "OPENAI_EMBEDDING_DIMENSIONS": (1, None),
    "CHUNK_SIZE_CHARS": (500, 8_000),
    "CHUNK_OVERLAP_CHARS": (0, 1_000),
    "SESSION_LIFETIME_DAYS": (1, 30),
}
FLOAT_RANGES = {
    "DATABASE_POOL_TIMEOUT_SECONDS": (0, 60),
    "DATABASE_STARTUP_TIMEOUT_SECONDS": (0, 60),
    "KESTRA_TIMEOUT_SECONDS": (0, 60),
    "OPENAI_TIMEOUT_SECONDS": (0, 120),
}
DECIMAL_FIELDS = {
    "DEFAULT_USER_LIFETIME_BUDGET_USD": True,
    "RESEARCH_COST_RESERVATION_USD": False,
    "CORPUS_PREPARATION_COST_RESERVATION_USD": False,
}


def validate_operator_values(values):
    for key, (minimum, maximum) in INTEGER_RANGES.items():
        try:
            value = int(values[key])
        except ValueError:
            raise ValueError(f"{key} must be an integer") from None
        if value < minimum or (maximum is not None and value > maximum):
            raise ValueError(f"{key} is outside its allowed range")
    if int(values["DATABASE_POOL_MAX_SIZE"]) < int(values["DATABASE_POOL_MIN_SIZE"]):
        raise ValueError("DATABASE_POOL_MAX_SIZE must be at least DATABASE_POOL_MIN_SIZE")
    for key, (minimum, maximum) in FLOAT_RANGES.items():
        try:
            value = float(values[key])
        except ValueError:
            raise ValueError(f"{key} must be a number") from None
        if not math.isfinite(value) or value <= minimum or value > maximum:
            raise ValueError(f"{key} is outside its allowed range")
    for key, allow_zero in DECIMAL_FIELDS.items():
        try:
            value = Decimal(values[key])
        except InvalidOperation:
            raise ValueError(f"{key} must be a decimal amount") from None
        if not value.is_finite() or value < 0 or (not allow_zero and value == 0):
            raise ValueError(f"{key} must be {'nonnegative' if allow_zero else 'positive'}")
    if values["LOG_LEVEL"] not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("LOG_LEVEL is invalid")
    if values["EDGAR_ACCESS_MODE"] != "CAUTION":
        raise ValueError("EDGAR_ACCESS_MODE must be CAUTION")


def read_input(path):
    values = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in FIELDS:
            raise ValueError(f"Unknown field or malformed assignment on line {number}")
        if key in values:
            raise ValueError(f"Duplicate field: {key}")
        if (
            not value
            or value != value.strip()
            or value.startswith(('"', "'"))
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise ValueError(f"Supply an unquoted, nonempty literal value for {key}")
        if re.search(r"<[^>]+>|change-me|replace-with|__required__", value):
            raise ValueError(f"Replace placeholder for {key}")
        values[key] = value
    for key in FIELDS:
        if key not in values:
            raise ValueError(f"Missing field: {key}")
    for key, minimum in (
        ("SESSION_SECRET", 32),
        ("INGESTION_API_TOKEN", 16),
        ("KESTRA_BASIC_AUTH_PASSWORD", 8),
    ):
        if len(values[key]) < minimum:
            raise ValueError(f"{key} must contain at least {minimum} characters")
    username = values["KESTRA_BASIC_AUTH_USERNAME"]
    if not EMAIL_RE.fullmatch(username):
        raise ValueError("KESTRA_BASIC_AUTH_USERNAME must be a valid email address")
    # These values are substituted into unquoted Kestra YAML at runtime.
    for key in (
        "KESTRA_DATABASE_PASSWORD",
        "KESTRA_BASIC_AUTH_PASSWORD",
    ):
        value = values[key]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", value) or value.lower() in YAML_PLAIN_WORDS:
            raise ValueError(
                f"{key} must start with a letter or underscore and use letters, digits, _ or -; avoid YAML boolean/null words"
            )
    password = values["KESTRA_BASIC_AUTH_PASSWORD"]
    if not re.search(r"[A-Z]", password) or not re.search(r"[0-9]", password):
        raise ValueError("KESTRA_BASIC_AUTH_PASSWORD requires an uppercase letter and digit")
    validate_operator_values(values)
    return values


def render(values):
    app = {
        key: values[key]
        for key in (
            "EDGAR_IDENTITY",
            "OPENAI_API_KEY",
            "INGESTION_API_TOKEN",
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "SESSION_SECRET",
            "GOOGLE_ADMIN_EMAILS",
            "KESTRA_BASIC_AUTH_USERNAME",
            "KESTRA_BASIC_AUTH_PASSWORD",
        )
    }
    app.update({key: values[key] for key in OPERATOR_FIELDS})
    app["DATABASE_URL"] = (
        "postgresql://sec_filings:"
        + quote(values["APP_DATABASE_PASSWORD"], safe="")
        + "@postgres:5432/sec_filings"
    )
    postgres = {
        "POSTGRES_PASSWORD": values["POSTGRES_PASSWORD"],
        "APP_DATABASE_NAME": "sec_filings",
        "APP_DATABASE_USER": "sec_filings",
        "APP_DATABASE_PASSWORD": values["APP_DATABASE_PASSWORD"],
        "KESTRA_DATABASE_NAME": "kestra",
        "KESTRA_DATABASE_USER": "kestra",
        "KESTRA_DATABASE_PASSWORD": values["KESTRA_DATABASE_PASSWORD"],
    }
    kestra = {
        key: postgres[key]
        for key in (
            "KESTRA_DATABASE_NAME",
            "KESTRA_DATABASE_USER",
            "KESTRA_DATABASE_PASSWORD",
        )
    }
    for key in ("KESTRA_BASIC_AUTH_USERNAME", "KESTRA_BASIC_AUTH_PASSWORD"):
        kestra[key] = values[key]
    kestra["SECRET_INGESTION_API_TOKEN"] = base64.b64encode(
        values["INGESTION_API_TOKEN"].encode("utf-8")
    ).decode("ascii")
    return {
        name: "".join(f"{key}={value}\n" for key, value in fields.items())
        for name, fields in (("app.env", app), ("postgres.env", postgres), ("kestra.env", kestra))
    }


def write_outputs(directory, outputs, overwrite):
    if directory.is_symlink():
        raise ValueError("Output directory must not be a symbolic link")
    for name in outputs:
        destination = directory / name
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise ValueError("Output destination must be a regular file")
        if destination.exists() and not overwrite:
            raise ValueError("Output files already exist; use --overwrite to regenerate")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    pending = []
    try:
        for name, content in outputs.items():
            fd, temporary = tempfile.mkstemp(prefix=".prepare-", dir=directory)
            pending.append((Path(temporary), directory / name))
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
        for temporary, destination in pending:
            if overwrite:
                os.replace(temporary, destination)
            else:
                # Exclusive creation also protects files created since the preflight check.
                os.link(temporary, destination)
                temporary.unlink()
    finally:
        for temporary, _ in pending:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(".env.prod"))
    parser.add_argument("--output-dir", type=Path, default=Path(".deploy-secrets"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        outputs = render(read_input(args.input))
        if args.input.resolve() in {(args.output_dir / name).resolve() for name in outputs}:
            raise ValueError("Input file must be separate from generated outputs")
        write_outputs(args.output_dir, outputs, args.overwrite)
    except (OSError, UnicodeError):
        print(
            "Credential preparation failed: check file access and UTF-8 encoding", file=sys.stderr
        )
        return 1
    except ValueError as exc:
        print(f"Credential preparation failed: {exc}", file=sys.stderr)
        return 1
    print("Prepared app.env, postgres.env, and kestra.env; no cluster changes made.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
