from __future__ import annotations

import base64
import importlib.util
import stat
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/prepare-deployment-secrets.py"
spec = importlib.util.spec_from_file_location("prepare_secrets", SCRIPT)
assert spec and spec.loader
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.fixture
def source(tmp_path: Path) -> Path:
    values = {key: "ExampleValue42" for key in helper.FIELDS}
    values.update(
        SESSION_SECRET="s" * 32,
        INGESTION_API_TOKEN="raw$token#with=equal",
        APP_DATABASE_PASSWORD="Example$@:#%/+=üPassword",
    )
    path = tmp_path / "input.env"
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
    return path


def test_round_trip_and_permissions(source: Path, tmp_path: Path) -> None:
    values = helper.read_input(source)
    outputs = helper.render(values)
    result = {
        name: dict(line.split("=", 1) for line in text.splitlines())
        for name, text in outputs.items()
    }
    app, pg, kestra = (result[n] for n in ("app.env", "postgres.env", "kestra.env"))
    assert unquote(urlsplit(app["DATABASE_URL"]).password) == pg["APP_DATABASE_PASSWORD"]
    assert "%24" in app["DATABASE_URL"]
    assert (
        base64.b64decode(kestra["SECRET_INGESTION_API_TOKEN"]).decode()
        == app["INGESTION_API_TOKEN"]
    )
    assert kestra["KESTRA_DATABASE_PASSWORD"] == pg["KESTRA_DATABASE_PASSWORD"]
    assert kestra["KESTRA_BASIC_AUTH_PASSWORD"] == app["KESTRA_BASIC_AUTH_PASSWORD"]
    assert pg["POSTGRES_PASSWORD"] != pg["APP_DATABASE_PASSWORD"]
    directory = tmp_path / "out"
    helper.write_outputs(directory, outputs, False)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in directory.iterdir())
    with pytest.raises(ValueError, match="already exist"):
        helper.write_outputs(directory, outputs, False)
    assert (directory / "app.env").read_text() == outputs["app.env"]
    helper.write_outputs(directory, outputs, True)
    assert not list(directory.glob(".prepare-*"))


@pytest.mark.parametrize(
    "change",
    [
        "duplicate",
        "missing",
        "placeholder",
        "short",
        "yaml",
        "quoted",
        "unknown",
    ],
)
def test_invalid_input_writes_nothing_and_does_not_echo_secrets(
    source: Path,
    tmp_path: Path,
    change: str,
) -> None:
    text = source.read_text()
    if change == "duplicate":
        text += "OPENAI_API_KEY=0123456789abcdef\n"
    elif change == "missing":
        text = "\n".join(
            line for line in text.splitlines() if not line.startswith("OPENAI_API_KEY=")
        )
    elif change == "placeholder":
        text = text.replace("OPENAI_API_KEY=ExampleValue42", "OPENAI_API_KEY=<REQUIRED>")
    elif change == "short":
        text = text.replace("SESSION_SECRET=" + "s" * 32, "SESSION_SECRET=SensitiveShort")
    elif change == "yaml":
        text = text.replace(
            "KESTRA_DATABASE_PASSWORD=ExampleValue42", "KESTRA_DATABASE_PASSWORD=true"
        )
    elif change == "quoted":
        text = text.replace("OPENAI_API_KEY=ExampleValue42", 'OPENAI_API_KEY="SensitiveQuoted"')
    else:
        text += "SensitiveUnknown=SensitiveValue\n"
    source.write_text(text)
    output = tmp_path / "out"
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(source), "--output-dir", str(output)],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 1
    assert not output.exists()
    assert "Sensitive" not in run.stdout + run.stderr
    assert "0123456789abcdef" not in run.stdout + run.stderr
    assert "ExampleValue42" not in run.stdout + run.stderr


def test_existing_symlink_rejected(source: Path, tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    (output / "app.env").symlink_to(source)
    original = source.read_text()
    with pytest.raises(ValueError, match="regular file"):
        helper.write_outputs(output, helper.render(helper.read_input(source)), True)
    assert source.read_text() == original


def test_generated_keys_match_existing_templates(source: Path) -> None:
    for name, content in helper.render(helper.read_input(source)).items():
        template = SCRIPT.parents[1] / "deploy/k3s/secrets" / (name + ".example")
        expected = {
            line.split("=", 1)[0]
            for line in template.read_text().splitlines()
            if line and not line.startswith("#")
        }
        assert {line.split("=", 1)[0] for line in content.splitlines()} == expected


def test_cli_success_hides_values_and_invalid_utf8_is_safe(source: Path, tmp_path: Path) -> None:
    args = [
        sys.executable,
        str(SCRIPT),
        "--input",
        str(source),
        "--output-dir",
        str(tmp_path / "out"),
    ]
    run = subprocess.run(args, text=True, capture_output=True)
    assert run.returncode == 0
    assert "ExampleValue42" not in run.stdout + run.stderr
    assert "raw$token" not in run.stdout + run.stderr
    source.write_bytes(b"OPENAI_API_KEY=SensitiveInvalid\xff")
    run = subprocess.run(args, text=True, capture_output=True)
    assert run.returncode == 1
    assert "SensitiveInvalid" not in run.stdout + run.stderr
