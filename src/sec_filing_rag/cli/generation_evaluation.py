from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from openai import OpenAI
from pydantic import ValidationError

from ..core.config import Settings
from ..core.pricing import load_pricing_configuration
from ..domain.filings import safe_error
from ..evaluation.generation import (
    GenerationEvaluationProgress,
    GenerationEvaluationRunner,
    artifact_markdown,
    emit_generation_evaluation_progress,
    load_generation_artifact,
    validate_artifact_inputs,
)
from ..evaluation.generation_live import (
    DatabaseGenerationEvaluationRepository,
    OpenAIAnswerProvider,
    OpenAIJudgeProvider,
)
from ..evaluation.service import (
    dataset_sha256,
    load_cases,
    load_manifest,
    validate_database_lineage,
    validate_review_gate,
)
from ..generation.service import load_generation_configuration
from ..repositories.database import Database
from ..retrieval.service import (
    OpenAIQueryEmbedder,
    RetrievalRepository,
    RetrievalService,
    load_retrieval_configuration,
)

DEFAULT_DATASET = Path("evaluation/retrieval-v1.jsonl")
DEFAULT_MANIFEST = Path("evaluation/retrieval-v1-manifest.json")
DEFAULT_RUBRIC = Path("evaluation/prompts/rag-judge-v1.txt")


def _elapsed(value: float) -> str:
    seconds = max(0, int(value))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_progress(event: GenerationEvaluationProgress) -> str:
    parts = ["generation-evaluation", _elapsed(event.elapsed_seconds)]
    if event.run_id is not None:
        parts.append(f"run {event.run_id}")
    if event.case_number is not None and event.case_count is not None:
        case = f"case {event.case_number}/{event.case_count}"
        if event.ticker:
            case += f" {event.ticker}"
        parts.append(case)
    elif event.case_count is not None and event.prompt_count is not None:
        parts.append(f"workload {event.case_count} cases x {event.prompt_count} prompts")
    if event.prompt_number is not None and event.prompt_count is not None:
        parts.append(f"prompt {event.prompt_number}/{event.prompt_count} {event.prompt_id}")
    if event.attempt is not None and event.max_attempts is not None:
        parts.append(f"attempt {event.attempt}/{event.max_attempts}")
    parts.append(event.stage.replace("_", " "))
    if event.total_prompt_cases:
        parts.append(f"completed {event.completed_prompt_cases}/{event.total_prompt_cases}")
    parts.append(f"failures {event.failure_count}")
    if event.status is not None:
        parts.append(f"status {event.status}")
    if event.selected_prompt_id is not None:
        parts.append(f"selected {event.selected_prompt_id}")
    elif event.stage in {"winner_selected", "run_finished", "output_writing", "output_written"}:
        parts.append("selected none")
    return " · ".join(parts)


def stderr_progress(event: GenerationEvaluationProgress) -> None:
    print(format_progress(event), file=sys.stderr, flush=True)


def _fail(error: BaseException | str) -> None:
    print(
        json.dumps({"status": "failed", "error": safe_error(error)}, sort_keys=True),
        file=sys.stderr,
    )
    raise SystemExit(2)


def _inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)


def validate_main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and render a generation-evaluation artifact"
    )
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--markdown", type=Path)
    _inputs(parser)
    args = parser.parse_args()
    try:
        artifact = load_generation_artifact(args.artifact)
        cases, manifest = load_cases(args.dataset), load_manifest(args.manifest)
        validate_artifact_inputs(artifact, cases, args.dataset, manifest)
        if args.markdown:
            if args.markdown.exists():
                raise ValueError("refusing to overwrite Markdown output")
            args.markdown.write_text(artifact_markdown(artifact), encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": "valid",
                    "cases": len(cases),
                    "selected_prompt_id": artifact.selected_prompt_id,
                },
                sort_keys=True,
            )
        )
    except (OSError, ValueError, ValidationError) as exc:
        _fail(exc)


def run_main() -> None:
    parser = argparse.ArgumentParser(description="Run controlled live full-RAG prompt evaluation")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    parser.add_argument("--prompt-id", action="append", default=[])
    parser.add_argument("--judge-prompt", type=Path, default=DEFAULT_RUBRIC)
    parser.add_argument("--workers", type=int, default=4, choices=range(1, 33))
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument(
        "--no-progress", action="store_true", help="suppress live progress on stderr"
    )
    _inputs(parser)
    args = parser.parse_args()
    database: Database | None = None
    embedder: OpenAIQueryEmbedder | None = None
    client: OpenAI | None = None
    progress_callback = None if args.validate_only or args.no_progress else stderr_progress
    progress_started = time.monotonic()

    def progress(stage: str, **values: Any) -> None:
        emit_generation_evaluation_progress(
            progress_callback,
            GenerationEvaluationProgress(
                stage=stage,
                elapsed_seconds=time.monotonic() - progress_started,
                **values,
            ),
        )

    def runner_progress(event: GenerationEvaluationProgress) -> None:
        if progress_callback is not None:
            progress_callback(replace(event, elapsed_seconds=time.monotonic() - progress_started))

    try:
        progress("preflight_started")
        if args.output_json == args.output_markdown:
            raise ValueError("JSON and Markdown output paths must differ")
        if args.output_json.exists() or args.output_markdown.exists():
            raise ValueError("refusing to overwrite an existing output path")
        settings = Settings()  # type: ignore[call-arg]
        retrieval_config = load_retrieval_configuration(settings.retrieval_config_path)
        generation_config = load_generation_configuration(settings.generation_config_path)
        prompt_ids = args.prompt_id or [entry.id for entry in generation_config.prompts]
        if len(prompt_ids) != len(set(prompt_ids)):
            raise ValueError("prompt IDs must be unique")
        for prompt_id in prompt_ids:
            generation_config.prompt(prompt_id)
        cases, manifest = load_cases(args.dataset), load_manifest(args.manifest)
        validate_review_gate(cases, manifest, args.dataset, retrieval_config)
        rubric = args.judge_prompt.read_text(encoding="utf-8")
        for field in ("{question}", "{answer}", "{reference_evidence}"):
            if field not in rubric:
                raise ValueError(f"judge rubric must contain {field}")
        pricing = load_pricing_configuration(settings.model_pricing_config_path)
        pricing_snapshot = pricing.snapshot_models(
            retrieval_config.embedding_model,
            settings.openai_chat_model,
            settings.resolved_judge_model,
        )
        database = Database(settings.database_url)
        workload_values = {
            "case_count": len(cases),
            "prompt_count": len(prompt_ids),
            "total_prompt_cases": len(cases) * len(prompt_ids),
        }
        progress("preflight_completed", **workload_values)
        progress("database_lineage_validation_started", **workload_values)
        validate_database_lineage(database, cases)
        progress("database_lineage_validation_completed", **workload_values)
        embedder = OpenAIQueryEmbedder(
            database,
            settings.openai_api_key,
            retrieval_config.embedding_model,
            retrieval_config.embedding_dimensions,
            settings.openai_timeout_seconds,
        )
        retrieval = RetrievalService(RetrievalRepository(database), embedder, retrieval_config)
        if args.validate_only:
            default = retrieval_config.default
            calls = {
                "cases": len(cases),
                "prompts": len(prompt_ids),
                "embedding_calls": len(cases) if default and default.strategy != "keyword" else 0,
                "generation_calls": len(cases) * len(prompt_ids),
                "judge_calls": len(cases) * len(prompt_ids),
            }
            print(
                json.dumps(
                    {
                        "status": "valid",
                        "provider_calls_made": 0,
                        "artifact_writes": 0,
                        "workers": args.workers,
                        **calls,
                    },
                    sort_keys=True,
                )
            )
            return
        client = OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
        runner = GenerationEvaluationRunner(
            DatabaseGenerationEvaluationRepository(database),
            retrieval,
            OpenAIAnswerProvider(client),
            OpenAIJudgeProvider(client),
            generation_config,
            generation_model=settings.openai_chat_model,
            judge_model=settings.resolved_judge_model,
            judge_rubric=rubric,
            pricing_snapshot=pricing_snapshot,
            progress_callback=runner_progress if progress_callback is not None else None,
        )
        artifact = runner.run(
            cases,
            prompt_ids,
            dataset_hash=dataset_sha256(args.dataset),
            corpus_hash=manifest.corpus_snapshot_sha256,
        )
        terminal_values = {
            "run_id": artifact.evaluation_run_id,
            "status": artifact.status,
            "selected_prompt_id": artifact.selected_prompt_id,
            "case_count": len(cases),
            "prompt_count": len(prompt_ids),
            "completed_prompt_cases": len(cases) * len(prompt_ids),
            "total_prompt_cases": len(cases) * len(prompt_ids),
            "failure_count": min(sum(row.failures for row in artifact.prompts), 100),
        }
        progress(
            "output_writing",
            **terminal_values,
        )
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(artifact.model_dump_json(indent=2) + "\n", encoding="utf-8")
        args.output_markdown.write_text(artifact_markdown(artifact), encoding="utf-8")
        progress(
            "output_written",
            **terminal_values,
        )
        print(
            json.dumps(
                {
                    "status": artifact.status,
                    "json": str(args.output_json),
                    "markdown": str(args.output_markdown),
                    "selected_prompt_id": artifact.selected_prompt_id,
                },
                sort_keys=True,
            )
        )
    except (OSError, ValueError, ValidationError, RuntimeError) as exc:
        _fail(exc)
    finally:
        if client is not None:
            client.close()
        if embedder is not None:
            embedder.close()
        if database is not None:
            database.close()


main = validate_main


if __name__ == "__main__":
    validate_main()
