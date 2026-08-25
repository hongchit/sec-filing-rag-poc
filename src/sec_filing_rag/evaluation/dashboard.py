from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..core.config import Settings
from ..repositories.database import Database
from .service import (
    CorpusManifest,
    EvaluationCase,
    dataset_sha256,
    load_cases,
    load_manifest,
    select_winner,
)


class ArtifactError(Exception):
    pass


class ArtifactMissing(ArtifactError):
    pass


class ArtifactConflict(ArtifactError):
    pass


class ResultArtifact(BaseModel):
    model_config = ConfigDict(extra="allow")
    evaluation_run_id: str
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    course_commit: str | None = None
    results: list[dict[str, Any]]
    selected_default: dict[str, Any]
    coverage: dict[str, Any] = {}
    warnings: list[dict[str, Any]] = []
    failures: list[Any] = []


class EvaluationSummary(BaseModel):
    run: dict[str, Any]
    coverage: dict[str, Any]
    warnings: list[dict[str, Any]]
    selected_default_id: str
    strategy_best: dict[str, str]
    configurations: list[dict[str, Any]]
    lineage: dict[str, Any]


class EvaluationCases(BaseModel):
    configuration_id: str
    cases: list[dict[str, Any]]
    facets: dict[str, list[str]]
    warnings: list[dict[str, Any]]


class EvaluationChunk(BaseModel):
    chunk_id: str
    text: str
    preview: str
    citation: str
    ticker: str
    item: str
    accession: str
    source_url: str
    provenance: dict[str, Any]


def configuration_id(configuration: dict[str, Any]) -> str:
    canonical = json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()
    return f"cfg-{hashlib.sha256(canonical).hexdigest()[:16]}"


def preview(text: str, limit: int = 240) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 1].rstrip() + "…"


class EvaluationDashboardService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database, self.settings = database, settings

    def _load(self) -> tuple[ResultArtifact, list[EvaluationCase], CorpusManifest]:
        paths = (
            self.settings.retrieval_evaluation_result_path,
            self.settings.retrieval_evaluation_dataset_path,
            self.settings.retrieval_evaluation_manifest_path,
        )
        if any(not path.is_file() for path in paths):
            raise ArtifactMissing("current retrieval evaluation artifacts are unavailable")
        try:
            result = ResultArtifact.model_validate_json(paths[0].read_text(encoding="utf-8"))
            cases = load_cases(paths[1])
            manifest = load_manifest(paths[2])
        except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
            raise ArtifactConflict("current retrieval evaluation artifacts are malformed") from exc
        actual_hash = dataset_sha256(paths[1])
        if result.dataset_sha256 != actual_hash or manifest.dataset_sha256 != actual_hash:
            raise ArtifactConflict(
                "evaluation dataset checksum does not match the result and manifest"
            )
        case_ids = {case.id for case in cases}
        if not result.results or any(
            {question.get("case_id") for question in row.get("questions", [])} != case_ids
            for row in result.results
        ):
            raise ArtifactConflict("evaluation rankings do not contain exactly the reviewed cases")
        winner = select_winner(result.results)
        if winner["configuration"] != result.selected_default:
            raise ArtifactConflict("selected default does not follow the official ranking rules")
        return result, cases, manifest

    def _run(self, result: ResultArtifact) -> dict[str, Any]:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT id,status::text AS status,dataset_sha256,configuration_sha256,started_at,finished_at "
                "FROM public.retrieval_evaluation_run WHERE id=%s",
                (result.evaluation_run_id,),
            ).fetchone()
        if row is None:
            raise ArtifactConflict("evaluation run is absent from the database")
        if (
            str(row["dataset_sha256"]) != result.dataset_sha256
            or str(row["configuration_sha256"]) != result.configuration_sha256
        ):
            raise ArtifactConflict("evaluation run identity is inconsistent with the artifact")
        return {
            key: (
                value.isoformat()
                if hasattr(value, "isoformat")
                else str(value)
                if key == "id"
                else value
            )
            for key, value in row.items()
        }

    @staticmethod
    def _configs(result: ResultArtifact) -> list[dict[str, Any]]:
        official = sorted(
            result.results,
            key=lambda row: (
                -float(row["mrr"]),
                -float(row["hit_rate"]),
                float(row["median_latency_ms"]),
                {"keyword": 0, "vector": 1, "weighted_hybrid": 2, "rrf": 3}[
                    row["configuration"]["strategy"]
                ],
            ),
        )
        selected = configuration_id(result.selected_default)
        return [
            {
                "id": configuration_id(row["configuration"]),
                "official_rank": rank,
                "selected": configuration_id(row["configuration"]) == selected,
                **row["configuration"],
                "hit_rate": row["hit_rate"],
                "mrr": row["mrr"],
                "median_latency_ms": row["median_latency_ms"],
            }
            for rank, row in enumerate(official, 1)
        ]

    def summary(self) -> EvaluationSummary:
        result, cases, manifest = self._load()
        configurations = self._configs(result)
        best = {
            strategy: next(row["id"] for row in configurations if row["strategy"] == strategy)
            for strategy in ("keyword", "vector", "weighted_hybrid", "rrf")
        }
        return EvaluationSummary(
            run={
                **self._run(result),
                "course_commit": result.course_commit,
                "question_count": len(cases),
            },
            coverage=manifest.coverage,
            warnings=[*manifest.warnings, *result.warnings],
            selected_default_id=configuration_id(result.selected_default),
            strategy_best=best,
            configurations=configurations,
            lineage={
                "dataset_sha256": result.dataset_sha256,
                "configuration_sha256": result.configuration_sha256,
                "corpus_snapshot_sha256": manifest.corpus_snapshot_sha256,
                "parser_version": manifest.parser_version,
                "chunking_version": manifest.chunking_version,
                "embedding_model": manifest.embedding_model,
                "embedding_dimensions": manifest.embedding_dimensions,
                "corpora": [entry.model_dump(mode="json") for entry in manifest.corpora],
            },
        )

    def _chunks(self, ids: set[str]) -> dict[str, dict[str, Any]]:
        if not ids:
            return {}
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT gd.chunk_id,gd.text_content,gd.citation_handle,gd.item,gd.provenance,c.ticker,"
                "f.accession,f.source_url FROM gold.search_document gd JOIN public.company c ON c.id=gd.company_id "
                "JOIN silver.filing f ON f.id=gd.filing_id WHERE gd.chunk_id=ANY(%s)",
                (sorted(ids),),
            ).fetchall()
        return {str(row["chunk_id"]): dict(row) for row in rows}

    @staticmethod
    def _chunk(
        row: dict[str, Any] | None, chunk_id: str, *, rank: int | None = None, matched: bool = False
    ) -> dict[str, Any]:
        if row is None:
            return {
                "chunk_id": chunk_id,
                "missing": True,
                "rank": rank,
                "matched": matched,
                "preview": "Referenced chunk is missing",
            }
        return {
            "chunk_id": chunk_id,
            "missing": False,
            "rank": rank,
            "matched": matched,
            "preview": preview(str(row["text_content"])),
            "citation": row["citation_handle"],
            "ticker": row["ticker"],
            "item": row["item"],
            "accession": row["accession"],
            "source_url": row["source_url"],
        }

    def cases(self, config_id: str) -> EvaluationCases:
        result, cases, _ = self._load()
        row = next(
            (
                item
                for item in result.results
                if configuration_id(item["configuration"]) == config_id
            ),
            None,
        )
        if row is None:
            raise ArtifactMissing("unknown current evaluation configuration")
        questions = {item["case_id"]: item for item in row["questions"]}
        all_ids = {chunk for case in cases for chunk in case.relevant_chunk_ids}
        all_ids |= {chunk for question in questions.values() for chunk in question["chunk_ids"]}
        chunks = self._chunks(all_ids)
        missing = sorted(all_ids - chunks.keys())
        output: list[dict[str, Any]] = []
        for case in cases:
            question = questions[case.id]
            ranked = question["chunk_ids"]
            first = next(
                (i for i, chunk in enumerate(ranked, 1) if chunk in case.relevant_chunk_ids), None
            )
            output.append(
                {
                    "id": case.id,
                    "question": case.question,
                    "ticker": case.ticker,
                    "items": sorted(case.allowed_items),
                    "goal": case.goal,
                    "query_type": case.query_type,
                    "accession": case.accession,
                    "outcome": "miss"
                    if first is None
                    else "rank_one"
                    if first == 1
                    else "later_hit",
                    "first_relevant_rank": first,
                    "expected": [
                        self._chunk(chunks.get(chunk), chunk, matched=True)
                        for chunk in sorted(case.relevant_chunk_ids)
                    ],
                    "retrieved": [
                        self._chunk(
                            chunks.get(chunk),
                            chunk,
                            rank=i,
                            matched=chunk in case.relevant_chunk_ids,
                        )
                        for i, chunk in enumerate(ranked, 1)
                    ],
                }
            )
        output.sort(
            key=lambda item: (
                {"miss": 0, "later_hit": 1, "rank_one": 2}[item["outcome"]],
                -(item["first_relevant_rank"] or 999),
                item["id"],
            )
        )
        return EvaluationCases(
            configuration_id=config_id,
            cases=output,
            facets={
                "tickers": sorted({case.ticker for case in cases}),
                "items": sorted({item for case in cases for item in case.allowed_items}),
                "goals": sorted({case.goal for case in cases}),
                "query_types": sorted({case.query_type for case in cases}),
            },
            warnings=[
                {
                    "code": "missing_chunk",
                    "message": f"Referenced chunk {chunk} is missing",
                    "chunk_id": chunk,
                }
                for chunk in missing
            ],
        )

    def chunk(self, chunk_id: str) -> EvaluationChunk:
        result, cases, _ = self._load()
        allowed = {chunk for case in cases for chunk in case.relevant_chunk_ids}
        allowed |= {
            chunk
            for row in result.results
            for question in row["questions"]
            for chunk in question["chunk_ids"]
        }
        if chunk_id not in allowed:
            raise ArtifactMissing("chunk is not referenced by the current evaluation")
        row = self._chunks({chunk_id}).get(chunk_id)
        if row is None:
            raise ArtifactMissing("referenced chunk is missing")
        return EvaluationChunk(
            chunk_id=chunk_id,
            text=str(row["text_content"]),
            preview=preview(str(row["text_content"])),
            citation=str(row["citation_handle"]),
            ticker=str(row["ticker"]),
            item=str(row["item"]),
            accession=str(row["accession"]),
            source_url=str(row["source_url"]),
            provenance=dict(row["provenance"]),
        )
