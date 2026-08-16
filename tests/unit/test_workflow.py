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
    schedule = next(
        line.split("=", 1)[1]
        for line in example
        if line.startswith("ENV_INGESTION_SCHEDULE=")
    )
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
