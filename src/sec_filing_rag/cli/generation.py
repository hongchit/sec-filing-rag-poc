from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from ..main import create_app

ROOT = Path(__file__).resolve().parents[3]
OPENAPI_PATH = ROOT / "api" / "openapi.yaml"
HTTP_PATH = ROOT / "api" / "sec-filing-rag.http"


def _write_or_check(path: Path, content: str, *, check: bool) -> None:
    if check:
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            raise SystemExit(f"generated artifact is stale: {path.relative_to(ROOT)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def export_openapi(*, check: bool = False) -> None:
    content = yaml.safe_dump(create_app().openapi(), sort_keys=False, allow_unicode=True, width=110)
    _write_or_check(OPENAPI_PATH, content, check=check)


def generate_http(*, check: bool = False) -> None:
    if not OPENAPI_PATH.exists():
        export_openapi()
    executable = shutil.which("httpgenerator")
    if executable is None:
        raise SystemExit("httpgenerator is required; rebuild the Dev Container")
    with tempfile.TemporaryDirectory(prefix="sec-rag-http-") as directory:
        subprocess.run(
            [
                executable,
                str(OPENAPI_PATH),
                "--output",
                directory,
                "--output-type",
                "OneFile",
                "--base-url",
                "{{baseUrl}}",
                "--load-authorization-header-from-environment",
                "--authorization-header-variable-name",
                "internalToken",
                "--no-logging",
                "--skip-validation",
            ],
            check=True,
        )
        generated = list(Path(directory).glob("*.http"))
        if len(generated) != 1:
            raise SystemExit("httpgenerator did not produce exactly one REST Client file")
        content = generated[0].read_text(encoding="utf-8").rstrip() + "\n"
        generated_header = "@baseUrl = {{baseUrl}}\n"
        # The httpgenerator tool does not support environment variable substitution in the
        # generated file, so we need to replace the baseUrl and internalToken with environment
        # variable references.
        environment_header = (
            "@baseUrl = http://{{$processEnv APP_HOST}}:{{$processEnv APP_PORT}}\n"
            "@internalToken = {{$processEnv INGESTION_API_TOKEN}}\n"
        )
        if not content.startswith(generated_header):
            raise SystemExit("httpgenerator produced an unexpected header")
        content = environment_header + content.removeprefix(generated_header)
        _write_or_check(HTTP_PATH, content, check=check)


def openapi_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    export_openapi(check=parser.parse_args().check)


def http_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    generate_http(check=parser.parse_args().check)
