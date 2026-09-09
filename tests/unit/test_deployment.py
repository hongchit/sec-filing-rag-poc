from __future__ import annotations

import re
from pathlib import Path

import yaml


def test_production_dockerfile_uses_selective_copies_and_no_secret_inputs() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert not re.search(r"^\s*(?:COPY|ADD)\s+\.\s", dockerfile, flags=re.MULTILINE)
    assert not re.search(
        r"^\s*(?:ARG|ENV)\s+.*(?:SECRET|PASSWORD|TOKEN|API_KEY)",
        dockerfile,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    assert "FRONTEND_DIST_PATH=/app/frontend" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert dockerfile.count("@sha256:") == 3


def test_deployment_manifests_reference_secrets_without_defining_them() -> None:
    manifests = sorted(Path("deploy/k3s").glob("**/*.yaml"))
    documents = [
        document
        for path in manifests
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
        if isinstance(document, dict)
    ]

    assert all(document.get("kind") != "Secret" for document in documents)
    assert {"sec-rag-app", "sec-rag-postgres", "sec-rag-kestra"} <= {
        match
        for path in manifests
        for match in re.findall(
            r"name:\s+(sec-rag-(?:app|postgres|kestra))", path.read_text(encoding="utf-8")
        )
    }
    assert "tls.secretName" not in "\n".join(path.read_text(encoding="utf-8") for path in manifests)


def test_production_overlay_has_concrete_origin_and_immutable_digests() -> None:
    directory = Path("deploy/k3s/overlays/production")
    content = "\n".join(path.read_text(encoding="utf-8") for path in directory.glob("*.yaml"))

    assert "https://sec-filing-rag-poc.henrychan.dev" in content
    assert "host: sec-filing-rag-poc.henrychan.dev" in content
    assert len(re.findall(r"digest: sha256:[0-9a-f]{64}$", content, flags=re.MULTILINE)) == 2
    assert "sha256:" + "0" * 64 not in content


def test_publish_workflow_scans_before_registry_login() -> None:
    workflow = Path(".github/workflows/publish-images.yml").read_text(encoding="utf-8")

    assert "gitleaks/gitleaks-action" not in workflow
    assert "scan-source" not in workflow
    assert workflow.index("Scan image layers for secrets") < workflow.index("Sign in to GHCR")
    assert workflow.index("Inspect image metadata and filesystem") < workflow.index(
        "Sign in to GHCR"
    )
    assert not re.search(r"uses:\s+[^\s]+@(v|main|master)(?:\s|$)", workflow)


def test_secret_scanning_workflow_runs_only_for_pull_requests() -> None:
    workflow = Path(".github/workflows/security.yml").read_text(encoding="utf-8")

    assert re.search(r"^on:\n  pull_request:\n\npermissions:", workflow, flags=re.MULTILINE)
    assert "push:" not in workflow
    assert "workflow_dispatch:" not in workflow
    assert "fetch-depth: 0" in workflow
    assert "gitleaks/gitleaks-action" in workflow
    assert "# v3.0.0" in workflow
    assert not re.search(r"uses:\s+[^\s]+@(v|main|master)(?:\s|$)", workflow)


def test_postgres_entrypoint_can_prepare_volume_and_drop_privileges() -> None:
    documents = list(yaml.safe_load_all(Path("deploy/k3s/base/postgres.yaml").read_text()))
    statefulset = next(document for document in documents if document["kind"] == "StatefulSet")
    pod = statefulset["spec"]["template"]["spec"]
    container = pod["containers"][0]
    security = container["securityContext"]
    assert security["runAsUser"] == 0
    assert security["runAsGroup"] == 0
    assert security["allowPrivilegeEscalation"] is False
    assert security["capabilities"]["drop"] == ["ALL"]
    assert set(security["capabilities"]["add"]) == {
        "CHOWN",
        "FOWNER",
        "DAC_OVERRIDE",
        "SETUID",
        "SETGID",
    }
    assert not security.get("privileged", False)
    assert pod["volumes"][0]["persistentVolumeClaim"]["claimName"] == "postgres-data"


def test_app_disables_service_links_for_migration_settings() -> None:
    documents = list(yaml.safe_load_all(Path("deploy/k3s/base/app.yaml").read_text()))
    app = next(document for document in documents if document["kind"] == "Deployment")
    assert app["spec"]["template"]["spec"]["enableServiceLinks"] is False


def test_app_mounts_one_gib_persistent_active_evaluation_release() -> None:
    storage = list(yaml.safe_load_all(Path("deploy/k3s/base/storage.yaml").read_text()))
    claim = next(document for document in storage if document["metadata"]["name"] == "evaluation-data")
    assert claim["metadata"]["annotations"]["kustomize.toolkit.fluxcd.io/prune"] == "disabled"
    assert claim["spec"]["resources"]["requests"]["storage"] == "1Gi"
    documents = list(yaml.safe_load_all(Path("deploy/k3s/base/app.yaml").read_text()))
    app = next(document for document in documents if document["kind"] == "Deployment")
    pod = app["spec"]["template"]["spec"]
    container = pod["containers"][0]
    initializer = next(
        item for item in pod["initContainers"] if item["name"] == "initialize-evaluation"
    )
    assert initializer["command"] == ["sec-rag-production-evaluation", "initialize"]
    assert initializer["volumeMounts"] == [
        {"name": "evaluation-data", "mountPath": "/app/evaluation-data"}
    ]
    assert {mount["mountPath"] for mount in container["volumeMounts"]} >= {"/app/evaluation-data"}
    assert {volume["name"] for volume in pod["volumes"]} >= {"evaluation-data"}
    environment = {entry["name"]: entry["value"] for entry in container["env"]}
    assert environment["RETRIEVAL_CONFIG_PATH"] == "/app/evaluation-data/active/config/retrieval.json"
    assert environment["GENERATION_CONFIG_PATH"] == "/app/evaluation-data/active/config/generation.json"
    assert container["resources"]["limits"]["memory"] == "750Mi"

    profile = list(yaml.safe_load_all(Path("deploy/k3s/overlays/8gb/resources.yaml").read_text()))
    app_patch = next(document for document in profile if document["kind"] == "Deployment" and document["metadata"]["name"] == "app")
    assert app_patch["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["memory"] == "750Mi"


def test_single_replica_deployments_do_not_surge_against_quota() -> None:
    for name in ("app", "kestra"):
        documents = yaml.safe_load_all(Path(f"deploy/k3s/base/{name}.yaml").read_text())
        deployment = next(doc for doc in documents if doc["kind"] == "Deployment")
        assert deployment["spec"]["replicas"] == 1
        assert deployment["spec"]["strategy"] == {
            "type": "RollingUpdate",
            "rollingUpdate": {"maxSurge": 0, "maxUnavailable": 1},
        }
