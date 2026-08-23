from pathlib import Path

import yaml


def test_batch_flow_is_sequential_and_uses_only_protected_reference_contracts() -> None:
    path = Path("workflows/filing_batch.yaml")
    flow = yaml.safe_load(path.read_text())
    assert flow["inputs"] == [{"id": "batch_id", "type": "STRING"}]
    each = next(task for task in flow["tasks"] if task["id"] == "execute_items")
    assert each["concurrencyLimit"] == 1
    text = path.read_text()
    assert "internal/providers/filing-items" in text
    assert "internal/corpus-executions" in text
    assert "internal/filing-items" in text
    assert "internal/filing-batches" in text
    assert "secret('INGESTION_API_TOKEN')" in text
    assert "execution.id" in text
    assert "| toJson" in text
    for forbidden in ("filing_html", "provider_payload", "change-me", "/internal/ingestions"):
        assert forbidden not in text


def test_batch_flow_has_retry_continue_and_lifecycle_finalization() -> None:
    flow = yaml.safe_load(Path("workflows/filing_batch.yaml").read_text())
    retry = flow["tasks"][0]["retry"]
    each = next(task for task in flow["tasks"] if task["id"] == "execute_items")
    assert each["errors"][0]["allowFailure"] is True
    assert flow["finally"][0]["id"] == "finalize_batch"
    assert "errors" not in flow
    assert each["errors"][0]["retry"]["maxAttempts"] == 3
    assert flow["finally"][0]["retry"]["maxAttempts"] == 3
    assert retry["maxAttempts"] == 3
    assert "maxAttempt" not in retry


def test_batch_flow_resolves_dynamic_outputs_and_nested_loop_values() -> None:
    flow = yaml.safe_load(Path("workflows/filing_batch.yaml").read_text())
    each = next(task for task in flow["tasks"] if task["id"] == "execute_items")
    select, if_selected = each["tasks"]
    acquire, process = if_selected["then"]
    fail_item = each["errors"][0]

    assert "{{ taskrun.value }}" in select["uri"]
    assert if_selected["condition"] == (
        "{{ outputs.select[taskrun.value].body | jq('.status') | first == 'selected' }}"
    )
    assert "{{ parent.taskrun.value }}" in acquire["uri"]
    assert "{{ parent.taskrun.value }}" in process["uri"]
    assert "{{ taskrun.value }}" in fail_item["uri"]


def test_devcontainer_pins_httpgenerator_and_has_no_obsolete_flow_setting() -> None:
    post_create = Path(".devcontainer/post-create.sh").read_text()
    assert "cargo install httpgenerator --version 1.1.0 --locked" in post_create
    assert "features/rust:1" in Path(".devcontainer/devcontainer.json").read_text()
    environment = Path(".env.example").read_text()
    assert "KESTRA_BATCH_FLOW_ID=filing_batch" in environment
    assert "KESTRA_HISTORICAL_FLOW_ID" not in environment
