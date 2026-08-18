from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import NoReturn

from pydantic import ValidationError

from .config import Settings
from .domain import safe_error, sha256_bytes
from .ground_truth import (
    GenerationConfiguration,
    GroundTruthRepository,
    OpenAIAssessor,
    canonical_sha256,
    finalize_bundle,
    generate_bundle,
    load_bundle,
    validate_review,
)
from .repositories import Database


def fail(error: BaseException | str) -> NoReturn:
    print(json.dumps({"status": "failed", "error": safe_error(error)}, sort_keys=True), file=sys.stderr)
    raise SystemExit(2)


def common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--review-bundle", type=Path, default=Path("evaluation/ground-truth-review-v1.json"))
    parser.add_argument("--config", type=Path, default=Path("config/ground-truth.json"))
    parser.add_argument("--prompt", type=Path, default=Path("evaluation/prompts/investor-questions-v1.txt"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and human-review SEC retrieval ground truth")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="snapshot ready corpora and generate a review bundle")
    common_paths(generate)
    generate.add_argument(
        "--diagnostic", type=Path, default=Path("evaluation/ground-truth-generation-failure.json")
    )
    generate.add_argument("--run-id", type=uuid.UUID)
    generate.add_argument("--resume", action="store_true", help="reuse a valid existing review bundle")
    validate = commands.add_parser("validate-review", help="validate review-bundle structure and decisions")
    common_paths(validate)
    validate.add_argument("--allow-pending", action="store_true")
    finalize = commands.add_parser("finalize", help="create retrieval JSONL from accepted human reviews")
    common_paths(finalize)
    finalize.add_argument("--dataset", type=Path, default=Path("evaluation/retrieval-v1.jsonl"))
    finalize.add_argument("--manifest", type=Path, default=Path("evaluation/retrieval-v1-manifest.json"))
    args = parser.parse_args()
    try:
        settings = Settings()  # type: ignore[call-arg]
        repository = GroundTruthRepository(Database(settings.database_url))
        if args.command == "generate":
            config = GenerationConfiguration.model_validate_json(args.config.read_text(encoding="utf-8"))
            prompt = args.prompt.read_text(encoding="utf-8")
            prompt_sha = sha256_bytes(prompt.encode())
            if args.resume and args.review_bundle.exists():
                existing = load_bundle(args.review_bundle)
                validate_review(existing, require_complete=False)
                corpora, _ = repository.snapshot()
                snapshot_sha = canonical_sha256([corpus.model_dump(mode="json") for corpus in corpora])
                if (
                    existing.configuration != config
                    or existing.prompt_sha256 != prompt_sha
                    or existing.corpus_snapshot_sha256 != snapshot_sha
                ):
                    raise ValueError(
                        "existing review bundle does not match the current configuration, prompt, or corpora"
                    )
                print(
                    json.dumps(
                        {
                            "status": "resumed",
                            "generation_run_id": str(existing.generation_run_id),
                            "review_bundle": str(args.review_bundle),
                            "warnings": existing.shortfall_warnings(),
                        },
                        sort_keys=True,
                    )
                )
                return
            assessor = OpenAIAssessor(
                repository, settings.openai_api_key, config, prompt, settings.openai_timeout_seconds
            )
            try:
                bundle = generate_bundle(repository, assessor, config, prompt_sha, args.run_id)
            except Exception as exc:
                args.diagnostic.parent.mkdir(parents=True, exist_ok=True)
                args.diagnostic.write_text(
                    json.dumps(
                        {
                            "status": "failed",
                            "error": safe_error(exc),
                            "decisions": getattr(exc, "diagnostics", {}),
                        },
                        sort_keys=True,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                raise
            args.review_bundle.parent.mkdir(parents=True, exist_ok=True)
            args.review_bundle.write_text(bundle.model_dump_json(indent=2) + "\n", encoding="utf-8")
            print(
                json.dumps(
                    {
                        "status": "generated",
                        "generation_run_id": str(bundle.generation_run_id),
                        "selected_chunks": len(bundle.chunks),
                        "questions": sum(len(chunk.questions) for chunk in bundle.chunks),
                        "review_bundle": str(args.review_bundle),
                        "warnings": bundle.shortfall_warnings(),
                    },
                    sort_keys=True,
                )
            )
        elif args.command == "validate-review":
            bundle = load_bundle(args.review_bundle)
            validate_review(bundle, require_complete=not args.allow_pending)
            print(
                json.dumps(
                    {
                        "status": "valid",
                        "chunks": len(bundle.chunks),
                        "questions": sum(len(chunk.questions) for chunk in bundle.chunks),
                        "warnings": bundle.shortfall_warnings(),
                    },
                    sort_keys=True,
                )
            )
        else:
            bundle = load_bundle(args.review_bundle)
            args.dataset.parent.mkdir(parents=True, exist_ok=True)
            args.manifest.parent.mkdir(parents=True, exist_ok=True)
            records, manifest = finalize_bundle(
                bundle, repository, args.dataset, args.manifest, args.prompt, args.config
            )
            print(
                json.dumps(
                    {
                        "status": "finalized",
                        "cases": len(records),
                        "dataset": str(args.dataset),
                        "manifest": str(args.manifest),
                        "warnings": manifest["warnings"],
                    },
                    sort_keys=True,
                )
            )
    except (OSError, ValueError, ValidationError, RuntimeError) as exc:
        fail(exc)
