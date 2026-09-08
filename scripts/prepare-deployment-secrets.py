#!/usr/bin/env python3
"""Derive Kubernetes env files from literal raw production credentials, offline."""

import argparse
import base64
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

FIELDS = (
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
    # These values are inserted into unquoted YAML by the existing Kestra manifest.
    for key in (
        "KESTRA_DATABASE_PASSWORD",
        "KESTRA_BASIC_AUTH_USERNAME",
        "KESTRA_BASIC_AUTH_PASSWORD",
    ):
        value = values[key]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", value) or value.lower() in {
            "true",
            "false",
            "null",
            "yes",
            "no",
            "on",
            "off",
        }:
            raise ValueError(
                f"{key} must start with a letter or underscore and use letters, digits, _ or -; avoid YAML boolean/null words"
            )
    password = values["KESTRA_BASIC_AUTH_PASSWORD"]
    if not re.search(r"[A-Z]", password) or not re.search(r"[0-9]", password):
        raise ValueError("KESTRA_BASIC_AUTH_PASSWORD requires an uppercase letter and digit")
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
