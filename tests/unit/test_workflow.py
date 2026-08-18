from pathlib import Path

import yaml


def test_kestra_flow_uses_internal_http_and_no_literal_secret() -> None:
    path = Path("workflows/ingest_corpus.yaml")
    flow = yaml.safe_load(path.read_text())
    task = flow["tasks"][0]
    assert task["type"] == "io.kestra.plugin.core.http.Request"
    assert task["uri"] == "http://app:8000/internal/ingestions"
    assert "secret('INGESTION_API_TOKEN')" in task["headers"]["Authorization"]
    assert "change-me" not in path.read_text()


def test_example_schedule_is_exposed_to_kestra_and_is_five_field_weekly_cron() -> None:
    example = Path(".env.example").read_text().splitlines()
    schedule = next(line.split("=", 1)[1] for line in example if line.startswith("ENV_INGESTION_SCHEDULE="))
    assert schedule == "0 6 * * 1"
    assert len(schedule.split()) == 5

    workflow = Path("workflows/ingest_corpus.yaml").read_text()
    assert 'cron: "{{ envs.ingestion_schedule }}"' in workflow


def test_corpus_flow_defaults_to_all_and_forces_all_for_schedule() -> None:
    flow = yaml.safe_load(Path("workflows/ingest_corpus.yaml").read_text())
    assert flow["inputs"] == [{"id": "target", "type": "STRING", "defaults": "all"}]
    body = flow["tasks"][0]["body"]
    assert 'trigger is defined ? "all" : inputs.target' in body
    assert '"trigger"' in body


def test_both_workflows_correlate_execution_and_only_call_protected_internal_endpoint() -> None:
    for filename in ("ingest_corpus.yaml", "prepare_historical_filing.yaml"):
        text = Path("workflows", filename).read_text()
        flow = yaml.safe_load(text)
        assert "execution.id" in text
        assert "| toJson" in text
        assert "| json" not in text
        assert "change-me" not in text
        for task in flow["tasks"]:
            assert task["uri"] == "http://app:8000/internal/ingestions"
            assert "secret('INGESTION_API_TOKEN')" in task["headers"]["Authorization"]


def test_historical_workflow_has_explicit_selection_inputs() -> None:
    flow = yaml.safe_load(Path("workflows/prepare_historical_filing.yaml").read_text())
    assert [entry["id"] for entry in flow["inputs"]] == [
        "preparation_request_id",
        "ticker",
        "requested_year",
        "selected_accession",
    ]


def test_environment_example_has_one_kestra_credential_pair_and_no_unused_aliases() -> None:
    text = Path(".env.example").read_text()
    assert text.count("KESTRA_BASIC_AUTH_USERNAME=") == 1
    assert text.count("KESTRA_BASIC_AUTH_PASSWORD=") == 1
    for removed in (
        "KESTRA_USERNAME=",
        "KESTRA_PASSWORD=",
        "APP_INTERNAL_URL=",
        "POSTGRES_HOST=",
        "POSTGRES_PORT=",
    ):
        assert removed not in text

    compose = Path(".devcontainer/docker-compose.yml").read_text()
    # Keep this literal: Compose interpolation prevented the Dev Container from starting.
    assert "image: kestra/kestra:v1.3.29" in compose
    assert "KESTRA_VERSION" not in compose
