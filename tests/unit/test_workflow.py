from pathlib import Path

import yaml

from sec_filing_rag.repositories.workflows import _aggregate_batch_status


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
    assert each["errors"][0]["retry"]["maxAttempts"] == 5
    assert flow["finally"][0]["retry"]["maxAttempts"] == 5
    assert retry["maxAttempts"] == 5
    assert "maxAttempt" not in retry


def test_every_workflow_retry_uses_the_exact_exponential_policy() -> None:
    expected = {
        "type": "exponential",
        "interval": "PT10S",
        "maxInterval": "PT1M",
        "delayFactor": 2,
        "maxAttempts": 5,
    }

    def retries(value):  # type: ignore[no-untyped-def]
        if isinstance(value, dict):
            if "retry" in value:
                yield value["retry"]
            for child in value.values():
                yield from retries(child)
        elif isinstance(value, list):
            for child in value:
                yield from retries(child)

    for path in Path("workflows").glob("*.yaml"):
        policies = list(retries(yaml.safe_load(path.read_text())))
        assert policies, f"{path} has no retry policies"
        assert all(policy == expected for policy in policies)
        assert "type: constant" not in path.read_text()


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


def test_devcontainer_installs_gitleaks_and_enables_staged_scan() -> None:
    dockerfile = Path(".devcontainer/Dockerfile").read_text()
    post_create = Path(".devcontainer/post-create.sh").read_text()
    hook_path = Path(".githooks/pre-commit")
    hook = hook_path.read_text()

    assert "GITLEAKS_VERSION=8.30.1" in dockerfile
    assert "GITLEAKS_SHA256_AMD64=551f6fc8" in dockerfile
    assert "GITLEAKS_SHA256_ARM64=e4a487ee" in dockerfile
    assert "sha256sum -c -" in dockerfile
    assert "Unsupported Gitleaks architecture" in dockerfile
    assert "gitleaks version" in dockerfile
    assert "config --local core.hooksPath .githooks" in post_create
    assert hook_path.stat().st_mode & 0o111
    assert "gitleaks git --pre-commit --staged --redact --config .gitleaks.toml ." in hook


def test_scheduled_launcher_reuses_batch_flow_with_daily_non_overlapping_trigger() -> None:
    path = Path("workflows/scheduled_filing_launcher.yaml")
    flow = yaml.safe_load(path.read_text())
    create_batch, process_batch = flow["tasks"]
    trigger = flow["triggers"][0]

    assert create_batch["uri"].endswith("/internal/scheduled-filing-batches")
    assert create_batch["headers"]["X-Kestra-Execution-ID"] == "{{ execution.id }}"
    assert process_batch["type"] == "io.kestra.plugin.core.flow.Subflow"
    assert process_batch["namespace"] == "sec_filings.ingestion"
    assert process_batch["flowId"] == "filing_batch"
    assert process_batch["wait"] is True
    assert process_batch["transmitFailed"] is True
    assert trigger == {
        "id": "daily_latest_filings",
        "type": "io.kestra.plugin.core.trigger.Schedule",
        "disabled": True,
        "cron": "8 6 * * *",
        "timezone": "Etc/UTC",
        "allowConcurrent": False,
        "recoverMissedSchedules": "LAST",
    }
    assert "secret('INGESTION_API_TOKEN')" in path.read_text()
    assert "launch-failures" in path.read_text()


def test_latest_batch_aggregation_treats_unchanged_items_as_success() -> None:
    assert _aggregate_batch_status("latest", {"skipped": 3}) == "succeeded"
    assert _aggregate_batch_status("latest", {"succeeded": 1, "skipped": 2}) == "succeeded"
    assert (
        _aggregate_batch_status("latest", {"succeeded": 1, "skipped": 1, "failed": 1})
        == "partial_failure"
    )


def test_exact_year_absence_and_real_failures_remain_non_success() -> None:
    assert _aggregate_batch_status("exact_year", {"skipped": 3}) == "failed"
    assert _aggregate_batch_status("latest", {"failed": 3}) == "failed"
