from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NoReturn

from pydantic import ValidationError

from ..core.config import Settings
from ..domain.filings import safe_error
from ..evaluation.service import (
    RetrievalEvaluator,
    dataset_sha256,
    load_cases,
    load_manifest,
    validate_database_lineage,
    validate_review_gate,
)
from ..repositories.database import Database
from ..retrieval.service import (
    OpenAIQueryEmbedder,
    RetrievalQuery,
    RetrievalRepository,
    RetrievalService,
    load_retrieval_configuration,
    result_as_dict,
)


def _fail(error: BaseException | str) -> NoReturn:
    print(json.dumps({"status": "failed", "error": safe_error(error)}, sort_keys=True), file=sys.stderr)
    raise SystemExit(2)


def _service(settings: Settings) -> tuple[Database, RetrievalService]:
    config = load_retrieval_configuration(settings.retrieval_config_path)
    database = Database(settings.database_url)
    embedder = OpenAIQueryEmbedder(
        database,
        settings.openai_api_key,
        config.embedding_model,
        config.embedding_dimensions,
        settings.openai_timeout_seconds,
    )
    return database, RetrievalService(RetrievalRepository(database), embedder, config)


def search_main() -> None:
    parser = argparse.ArgumentParser(description="Inspect corpus-scoped PostgreSQL retrieval")
    parser.add_argument("question")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--corpus-version-id", required=True)
    parser.add_argument("--strategy", choices=("keyword", "vector", "weighted_hybrid", "rrf"), default=None)
    parser.add_argument("--items", nargs="+")
    parser.add_argument("--candidate-count", type=int)
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--alpha", type=float)
    parser.add_argument("--rrf-k", type=int)
    args = parser.parse_args()
    database: Database | None = None
    service: RetrievalService | None = None
    try:
        settings = Settings()  # type: ignore[call-arg]
        database, service = _service(settings)
        default = service.config.default
        if args.strategy is None and default is None:
            raise ValueError("no measured default exists; pass --strategy before benchmark selection")
        selected = default
        query = RetrievalQuery(
            question=args.question,
            ticker=args.ticker,
            corpus_version_id=args.corpus_version_id,
            allowed_items=frozenset(args.items) if args.items else None,
            strategy=args.strategy or selected.strategy,  # type: ignore[union-attr]
            candidate_count=args.candidate_count or (selected.candidate_count if selected else 20),
            top_k=args.top_k or (selected.top_k if selected else 5),
            alpha=args.alpha
            if args.alpha is not None
            else (selected.alpha if selected and selected.alpha is not None else 0.5),
            rrf_k=args.rrf_k
            if args.rrf_k is not None
            else (selected.rrf_k if selected and selected.rrf_k is not None else 60),
        )
        payload = {
            "query": query.model_dump(mode="json"),
            "configuration_version": service.config.version,
            "results": [result_as_dict(result) for result in service.retrieve(query)],
        }
        print(json.dumps(payload, sort_keys=True, indent=2))
    except (ValueError, ValidationError, RuntimeError) as exc:
        _fail(exc)
    finally:
        if service is not None and isinstance(service.embedder, OpenAIQueryEmbedder):
            service.embedder.close()
        if database is not None:
            database.close()


def _markdown(artifact: dict[str, Any], command: str) -> str:
    winner = artifact["selected_default"]
    return (
        "# Retrieval evaluation\n\n"
        f"- Dataset SHA-256: `{artifact['dataset_sha256']}`\n"
        f"- Configuration SHA-256: `{artifact['configuration_sha256']}`\n"
        f"- Course commit: `{artifact['course_commit']}`\n"
        f"- Selected default: `{json.dumps(winner, sort_keys=True)}`\n"
        f"- Coverage warnings: `{json.dumps(artifact.get('warnings', []), sort_keys=True)}`\n"
        f"- Reproduce: `{command}`\n\n"
        "The selected configuration maximized MRR, then Hit Rate, then lower median latency, "
        "then strategy simplicity. See the adjacent JSON for per-question rankings and failures.\n"
    )


def evaluate_main() -> None:
    parser = argparse.ArgumentParser(description="Validate or benchmark reviewed retrieval ground truth")
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/retrieval-v1.jsonl"))
    parser.add_argument("--manifest", type=Path, default=Path("evaluation/retrieval-v1-manifest.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/results"))
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    database: Database | None = None
    service: RetrievalService | None = None
    try:
        settings = Settings()  # type: ignore[call-arg]
        database, service = _service(settings)
        cases, manifest = load_cases(args.dataset), load_manifest(args.manifest)
        validate_review_gate(cases, manifest, args.dataset, service.config)
        validate_database_lineage(database, cases)
        if args.validate_only:
            print(
                json.dumps(
                    {
                        "status": "valid",
                        "case_count": len(cases),
                        "coverage": manifest.coverage,
                        "warnings": manifest.warnings,
                    },
                    sort_keys=True,
                )
            )
            return
        artifact = RetrievalEvaluator(database, service, service.config).run(
            cases, dataset_sha256(args.dataset), manifest.coverage, manifest.warnings
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        json_path, markdown_path = args.output_dir / "retrieval-v1.json", args.output_dir / "retrieval-v1.md"
        json_path.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        command = (
            "uv run sec-rag-evaluate-retrieval --dataset evaluation/retrieval-v1.jsonl "
            "--manifest evaluation/retrieval-v1-manifest.json"
        )
        markdown_path.write_text(_markdown(artifact, command), encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": "succeeded",
                    "json": str(json_path),
                    "markdown": str(markdown_path),
                    "warnings": manifest.warnings,
                }
            )
        )
    except (OSError, ValueError, ValidationError, RuntimeError) as exc:
        _fail(exc)
    finally:
        if service is not None and isinstance(service.embedder, OpenAIQueryEmbedder):
            service.embedder.close()
        if database is not None:
            database.close()
