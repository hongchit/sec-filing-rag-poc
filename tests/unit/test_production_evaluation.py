from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from sec_filing_rag.cli import production_evaluation as production
from sec_filing_rag.generation.service import load_generation_configuration
from sec_filing_rag.retrieval.service import load_retrieval_configuration

ROOT = Path(__file__).resolve().parents[2]


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "image"
    shutil.copytree(ROOT / "config", source / "config")
    shutil.copytree(ROOT / "evaluation", source / "evaluation")
    return source


def _accepted_run(root: Path, source: Path, run_id: str) -> Path:
    production.initialize(root, source)
    production.create_run(root, run_id)
    run = root / "runs" / run_id
    retrieval = load_retrieval_configuration(run / "config/retrieval.json")
    retrieval_result = run / "evaluation/results/retrieval-v1.json"
    retrieval_result.parent.mkdir(parents=True, exist_ok=True)
    retrieval_data = json.loads(
        (source / "evaluation/results/retrieval-v1.json").read_text(encoding="utf-8")
    )
    retrieval_data["configuration_sha256"] = retrieval.sha256()
    retrieval_result.write_text(json.dumps(retrieval_data), encoding="utf-8")
    shutil.copy(source / "evaluation/results/retrieval-v1.md", retrieval_result.with_suffix(".md"))
    production.accept_retrieval(root, run_id)
    retrieval = load_retrieval_configuration(run / "config/retrieval.json")
    generation = load_generation_configuration(run / "config/generation.json")
    generation_result = run / "evaluation/results/generation-v1.json"
    generation_data = json.loads(
        (source / "evaluation/results/generation-v1.json").read_text(encoding="utf-8")
    )
    generation_data["retrieval_configuration_sha256"] = retrieval.sha256()
    generation_data["generation_configuration_sha256"] = generation.sha256()
    selected = generation_data["selected_prompt_id"]
    _, prompt_sha256 = generation.prompt(selected)
    for prompt in generation_data["prompts"]:
        if prompt["prompt_id"] == selected:
            prompt["prompt_sha256"] = prompt_sha256
    generation_result.write_text(json.dumps(generation_data), encoding="utf-8")
    shutil.copy(source / "evaluation/results/generation-v1.md", generation_result.with_suffix(".md"))
    return run


def test_initialize_create_and_status_do_not_expose_artifacts(tmp_path: Path) -> None:
    root, source = tmp_path / "data", _source(tmp_path)

    assert production.initialize(root, source) == {"status": "initialized", "active_release": "initial"}
    assert production.status(root) == {
        "status": "ready",
        "active_release": "initial",
        "required_artifacts_available": True,
        "missing_artifact_count": 0,
    }
    created = production.create_run(root, "run-one")
    assert created["status"] == "created"
    assert (root / "runs/run-one/config/prompts/basic-grounded-v2.txt").is_file()
    assert not (root / "runs/run-one/evaluation/results/retrieval-v1.json").exists()
    assert not (root / "runs/run-one/evaluation/results/generation-v1.json").exists()
    with pytest.raises(ValueError, match="already exists"):
        production.create_run(root, "run-one")


def test_publish_replaces_old_active_release_and_derives_promotions(tmp_path: Path) -> None:
    root, source = tmp_path / "data", _source(tmp_path)
    _accepted_run(root, source, "run-one")

    assert production.publish(root, "run-one") == {
        "status": "published",
        "active_release": "run-one",
        "prior_release_cleanup_pending": False,
    }
    assert root.joinpath("active").resolve() == root / "releases/run-one"
    assert not (root / "releases/initial").exists()
    retrieval = load_retrieval_configuration(root / "active/config/retrieval.json")
    generation = load_generation_configuration(root / "active/config/generation.json")
    assert retrieval.default is not None
    assert retrieval.default.reason == "Accepted production retrieval evaluation from release run-one."
    assert generation.promoted_prompt_id == "basic-grounded-v2"
    assert generation.promotion_reason == "Accepted production generation evaluation from release run-one."


def test_accept_retrieval_promotes_a_changed_winner_before_generation(tmp_path: Path) -> None:
    root, source = tmp_path / "data", _source(tmp_path)
    production.initialize(root, source)
    production.create_run(root, "changed-winner")
    run = root / "runs/changed-winner"
    retrieval = load_retrieval_configuration(run / "config/retrieval.json")
    result_path = run / "evaluation/results/retrieval-v1.json"
    result = json.loads((source / "evaluation/results/retrieval-v1.json").read_text(encoding="utf-8"))
    for row in result["results"]:
        row["mrr"] = 0.0
        row["hit_rate"] = 0.0
    changed = result["results"][0]
    changed["mrr"] = 1.0
    changed["hit_rate"] = 1.0
    result["selected_default"] = changed["configuration"]
    result["configuration_sha256"] = retrieval.sha256()
    result_path.write_text(json.dumps(result), encoding="utf-8")

    accepted = production.accept_retrieval(root, "changed-winner")

    promoted = load_retrieval_configuration(run / "config/retrieval.json")
    assert accepted["status"] == "retrieval_accepted"
    assert promoted.default is not None
    assert promoted.default.strategy == changed["configuration"]["strategy"]
    assert promoted.sha256() == accepted["retrieval_configuration_sha256"]
    assert production.accept_retrieval(root, "changed-winner")["status"] == "already_accepted"


def test_publish_leaves_active_release_unchanged_when_artifacts_are_incomplete(tmp_path: Path) -> None:
    root, source = tmp_path / "data", _source(tmp_path)
    production.initialize(root, source)
    production.create_run(root, "bad-run")

    with pytest.raises(ValueError, match="release is incomplete|retrieval result has not been accepted"):
        production.publish(root, "bad-run")
    assert root.joinpath("active").resolve() == root / "releases/initial"


def test_publish_rejects_generation_from_an_unaccepted_retrieval_config(tmp_path: Path) -> None:
    root, source = tmp_path / "data", _source(tmp_path)
    run = _accepted_run(root, source, "wrong-lineage")
    result_path = run / "evaluation/results/generation-v1.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["retrieval_configuration_sha256"] = "0" * 64
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(ValueError, match="retrieval configuration checksum does not match"):
        production.publish(root, "wrong-lineage")
    assert root.joinpath("active").resolve() == root / "releases/initial"
