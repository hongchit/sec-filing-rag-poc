"""Manage the single persistent production evaluation release without provider calls."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, NoReturn

from pydantic import ValidationError

from ..evaluation.generation import load_generation_artifact, validate_artifact_inputs
from ..evaluation.service import load_cases, load_manifest, select_winner, validate_review_gate
from ..generation.service import load_generation_configuration
from ..retrieval.service import SelectedRetrievalConfiguration, load_retrieval_configuration

DEFAULT_ROOT = Path("/app/evaluation-data")
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
REQUIRED_FILES = (
    "config/retrieval.json",
    "config/generation.json",
    "config/ground-truth.json",
    "config/prompts/basic-grounded-v1.txt",
    "config/prompts/basic-grounded-v2.txt",
    "config/prompts/guardrailed-10k-v3.txt",
    "evaluation/ground-truth-review-v1.json",
    "evaluation/prompts/investor-questions-v1.txt",
    "evaluation/prompts/rag-judge-v1.txt",
    "evaluation/retrieval-v1.jsonl",
    "evaluation/retrieval-v1-manifest.json",
    "evaluation/results/retrieval-v1.json",
    "evaluation/results/retrieval-v1.md",
    "evaluation/results/generation-v1.json",
    "evaluation/results/generation-v1.md",
)
RESULT_FILES = (
    "evaluation/results/retrieval-v1.json",
    "evaluation/results/retrieval-v1.md",
    "evaluation/results/generation-v1.json",
    "evaluation/results/generation-v1.md",
)
RUN_METADATA = ".production-evaluation.json"
RUN_METADATA_VERSION = "production-evaluation-run-v1"


def _fail(error: BaseException | str) -> NoReturn:
    print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True), file=sys.stderr)
    raise SystemExit(2)


def _release(root: Path) -> Path:
    active = root / "active"
    if not active.is_symlink() or not active.exists():
        raise ValueError("no active production evaluation release; run initialize first")
    return active.resolve()


def _run_id(value: str) -> str:
    if not RUN_ID_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("run ID must be 1-63 lowercase letters, digits, or hyphens")
    return value


def _copy_source(source: Path, destination: Path) -> None:
    for name in ("config", "evaluation"):
        shutil.copytree(source / name, destination / name)


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _write_model(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def initialize(root: Path, source: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    active = root / "active"
    if active.exists() or active.is_symlink():
        return {"status": "already_initialized", "active_release": _release(root).name}
    if not (source / "config").is_dir() or not (source / "evaluation").is_dir():
        raise ValueError("source must contain checked-in config and evaluation directories")
    releases = root / "releases"
    releases.mkdir(exist_ok=True)
    initial = releases / "initial"
    if initial.exists():
        raise ValueError("initial release exists without an active release; inspect persistent storage")
    _copy_source(source, initial)
    temporary = root / ".active-initial"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(Path("releases") / initial.name)
    os.replace(temporary, active)
    return {"status": "initialized", "active_release": initial.name}


def create_run(root: Path, run_id: str) -> dict[str, Any]:
    source = _release(root)
    destination = root / "runs" / run_id
    if destination.exists() or destination.is_symlink():
        raise ValueError("working run already exists")
    destination.parent.mkdir(exist_ok=True)
    shutil.copytree(source, destination)
    for name in RESULT_FILES:
        (destination / name).unlink(missing_ok=True)
    (destination / RUN_METADATA).unlink(missing_ok=True)
    return {"status": "created", "run_id": run_id, "path": str(destination)}


def _required(run: Path) -> None:
    missing = [name for name in REQUIRED_FILES if not (run / name).is_file()]
    if missing:
        raise ValueError("release is incomplete: " + ", ".join(missing))


def _retrieval_inputs(run: Path) -> tuple[Any, list[Any], Any, dict[str, Any]]:
    retrieval_path = run / "config/retrieval.json"
    dataset_path = run / "evaluation/retrieval-v1.jsonl"
    manifest_path = run / "evaluation/retrieval-v1-manifest.json"
    result_path = run / "evaluation/results/retrieval-v1.json"
    required = (retrieval_path, dataset_path, manifest_path, result_path)
    if any(not path.is_file() for path in required):
        raise ValueError("retrieval evaluation inputs or result are incomplete")
    retrieval = load_retrieval_configuration(retrieval_path)
    cases, manifest = load_cases(dataset_path), load_manifest(manifest_path)
    validate_review_gate(cases, manifest, dataset_path, retrieval)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("dataset_sha256") != manifest.dataset_sha256:
        raise ValueError("retrieval result dataset checksum does not match manifest")
    if result.get("failures"):
        raise ValueError("retrieval result contains failures")
    rows = result.get("results")
    if not isinstance(rows, list) or not rows:
        raise ValueError("retrieval result does not contain benchmark results")
    winner = select_winner(rows)["configuration"]
    if result.get("selected_default") != winner:
        raise ValueError("retrieval selected default does not match the benchmark winner")
    return retrieval, cases, manifest, result


def accept_retrieval(root: Path, run_id: str) -> dict[str, Any]:
    run = root / "runs" / run_id
    if not run.is_dir() or run.is_symlink():
        raise ValueError("working run does not exist")
    retrieval, _, _, result = _retrieval_inputs(run)
    result_sha = result.get("configuration_sha256")
    metadata_path = run / RUN_METADATA
    existing = (
        json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else None
    )
    selected = SelectedRetrievalConfiguration.model_validate(result.get("selected_default"))
    if selected.top_k > selected.candidate_count:
        raise ValueError("selected retrieval top_k exceeds candidate_count")
    selected.reason = f"Accepted production retrieval evaluation from release {run_id}."
    promoted = retrieval.model_copy(update={"default": selected})
    promoted = type(retrieval).model_validate(promoted.model_dump())
    current_sha = retrieval.sha256()
    if existing is not None:
        if (
            existing.get("version") != RUN_METADATA_VERSION
            or existing.get("run_id") != run_id
            or existing.get("retrieval_evaluation_configuration_sha256") != result_sha
            or existing.get("accepted_retrieval_configuration_sha256") != promoted.sha256()
        ):
            raise ValueError("working run retrieval acceptance metadata is inconsistent")
        if current_sha == promoted.sha256():
            return {
                "status": "already_accepted",
                "run_id": run_id,
                "retrieval_configuration_sha256": current_sha,
            }
        if current_sha != result_sha:
            raise ValueError("working retrieval configuration changed after evaluation")
    elif result_sha != current_sha:
        raise ValueError("retrieval result configuration checksum does not match")
    metadata = {
        "version": RUN_METADATA_VERSION,
        "run_id": run_id,
        "retrieval_evaluation_configuration_sha256": result_sha,
        "accepted_retrieval_configuration_sha256": promoted.sha256(),
    }
    _write_json(metadata_path, metadata)
    _write_model(run / "config/retrieval.json", promoted)
    load_retrieval_configuration(run / "config/retrieval.json")
    return {
        "status": "retrieval_accepted",
        "run_id": run_id,
        "retrieval_configuration_sha256": promoted.sha256(),
    }


def _validate_and_promote(run: Path, run_id: str) -> None:
    _required(run)
    generation_path = run / "config/generation.json"
    dataset_path = run / "evaluation/retrieval-v1.jsonl"
    generation_result_path = run / "evaluation/results/generation-v1.json"
    retrieval, cases, manifest, retrieval_result = _retrieval_inputs(run)
    generation = load_generation_configuration(generation_path)
    metadata_path = run / RUN_METADATA
    if not metadata_path.is_file():
        raise ValueError("retrieval result has not been accepted")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("version") != RUN_METADATA_VERSION or metadata.get("run_id") != run_id:
        raise ValueError("working run retrieval acceptance metadata is inconsistent")
    if metadata.get("retrieval_evaluation_configuration_sha256") != retrieval_result.get(
        "configuration_sha256"
    ):
        raise ValueError("retrieval evaluation lineage does not match acceptance metadata")
    if metadata.get("accepted_retrieval_configuration_sha256") != retrieval.sha256():
        raise ValueError("accepted retrieval configuration checksum does not match")
    selected = SelectedRetrievalConfiguration.model_validate(retrieval_result.get("selected_default"))
    if retrieval.default is None or retrieval.default.model_dump(exclude={"reason"}) != selected.model_dump(
        exclude={"reason"}
    ):
        raise ValueError("accepted retrieval default does not match the evaluated winner")
    artifact = load_generation_artifact(generation_result_path)
    validate_artifact_inputs(artifact, cases, dataset_path, manifest)
    if artifact.status != "succeeded" or artifact.selected_prompt_id is None:
        raise ValueError("generation result does not contain an accepted prompt")
    if artifact.retrieval_configuration_sha256 != retrieval.sha256():
        raise ValueError("generation result retrieval configuration checksum does not match")
    if artifact.generation_configuration_sha256 != generation.sha256():
        raise ValueError("generation result generation configuration checksum does not match")
    prompt = next((entry for entry in artifact.prompts if entry.prompt_id == artifact.selected_prompt_id), None)
    if prompt is None or not prompt.eligible:
        raise ValueError("generation selected prompt is not eligible")
    _, prompt_sha256 = generation.prompt(artifact.selected_prompt_id)
    if prompt.prompt_sha256 != prompt_sha256:
        raise ValueError("generation selected prompt source checksum does not match")
    generation.promoted_prompt_id = artifact.selected_prompt_id
    generation.promotion_reason = f"Accepted production generation evaluation from release {run_id}."
    _write_model(generation_path, generation)
    # Reloading catches serialization or persistent prompt-resolution mistakes before selection.
    reloaded_generation = load_generation_configuration(generation_path)
    reloaded_generation.prompt(artifact.selected_prompt_id)


def publish(root: Path, run_id: str) -> dict[str, Any]:
    working = root / "runs" / run_id
    if not working.is_dir() or working.is_symlink():
        raise ValueError("working run does not exist")
    _validate_and_promote(working, run_id)
    releases = root / "releases"
    releases.mkdir(exist_ok=True)
    destination = releases / run_id
    if destination.exists() or destination.is_symlink():
        raise ValueError("release ID has already been published")
    old = _release(root)
    if old.parent != releases.resolve():
        raise ValueError("active release points outside persistent release storage")
    os.replace(working, destination)
    temporary = root / ".active-next"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(Path("releases") / run_id)
    os.replace(temporary, root / "active")
    cleanup_pending = False
    if old != destination:
        try:
            shutil.rmtree(old)
        except OSError:
            cleanup_pending = True
    return {
        "status": "published",
        "active_release": run_id,
        "prior_release_cleanup_pending": cleanup_pending,
    }


def status(root: Path) -> dict[str, Any]:
    try:
        active = _release(root)
    except ValueError:
        return {"status": "uninitialized", "active_release": None, "required_artifacts_available": False}
    missing = [name for name in REQUIRED_FILES if not (active / name).is_file()]
    return {
        "status": "ready" if not missing else "incomplete",
        "active_release": active.name,
        "required_artifacts_available": not missing,
        "missing_artifact_count": len(missing),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the persistent production evaluation release")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    initial = commands.add_parser("initialize", help="seed persistent storage from image assets")
    initial.add_argument("--source", type=Path, default=Path("/app"))
    create = commands.add_parser("create-run", help="copy active release into an isolated working run")
    create.add_argument("run_id", type=_run_id)
    accept = commands.add_parser(
        "accept-retrieval", help="promote the reviewed retrieval winner inside a working run"
    )
    accept.add_argument("run_id", type=_run_id)
    publish_parser = commands.add_parser("publish", help="validate and atomically activate a working run")
    publish_parser.add_argument("run_id", type=_run_id)
    commands.add_parser("status", help="report active release and artifact availability")
    args = parser.parse_args()
    try:
        if args.command == "initialize":
            result = initialize(args.root, args.source)
        elif args.command == "create-run":
            result = create_run(args.root, args.run_id)
        elif args.command == "accept-retrieval":
            result = accept_retrieval(args.root, args.run_id)
        elif args.command == "publish":
            result = publish(args.root, args.run_id)
        else:
            result = status(args.root)
        print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        _fail(exc)


if __name__ == "__main__":
    main()
