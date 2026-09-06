from __future__ import annotations

from collections import Counter
from decimal import Decimal
from statistics import median
from typing import Any

from pydantic import BaseModel

from ..core.config import Settings
from ..core.pricing import estimate_charge
from ..generation.service import load_generation_configuration
from ..repositories.database import Database
from .dashboard import ArtifactConflict, ArtifactMissing, preview
from .generation import GenerationArtifact, PromptEvaluation, load_generation_artifact
from .service import EvaluationCase, dataset_sha256, load_cases, load_manifest


class GenerationEvaluationSummary(BaseModel):
    run: dict[str, Any]
    selected_prompt_id: str | None
    promoted_prompt_id: str | None
    prompts: list[dict[str, Any]]
    availability: dict[str, bool]
    warnings: list[dict[str, Any]]
    lineage: dict[str, Any]


class GenerationEvaluationCases(BaseModel):
    cases: list[dict[str, Any]]
    facets: dict[str, list[str]]
    warnings: list[dict[str, Any]]


class GenerationEvaluationQuestion(BaseModel):
    question: dict[str, Any]
    results: list[dict[str, Any]]
    expected: list[dict[str, Any]]
    retrieved: list[dict[str, Any]]
    evidence_available: bool
    warnings: list[dict[str, Any]]


class GenerationPromptSource(BaseModel):
    prompt_id: str
    prompt_sha256: str
    source: str


class GenerationEvaluationChunk(BaseModel):
    chunk_id: str
    corpus_version_id: str
    text: str
    preview: str
    citation: str
    ticker: str
    item: str
    accession: str
    source_url: str
    provenance: dict[str, Any]


def _recovery_warning(code: str, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "audience": "administrator",
        "recovery_docs": ["docs/getting-started.md", "docs/rag-evaluation-workflow.md"],
    }


class GenerationEvaluationDashboardService:
    """Serve portable generation artifacts with optional database evidence enrichment."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database, self.settings = database, settings

    def _load(self) -> tuple[GenerationArtifact, list[EvaluationCase]]:
        artifact_path = self.settings.generation_evaluation_result_path
        dataset_path = self.settings.retrieval_evaluation_dataset_path
        manifest_path = self.settings.retrieval_evaluation_manifest_path
        if any(not path.is_file() for path in (artifact_path, dataset_path, manifest_path)):
            raise ArtifactMissing("current generation evaluation artifacts are unavailable")
        try:
            artifact = load_generation_artifact(artifact_path)
            cases = load_cases(dataset_path)
            manifest = load_manifest(manifest_path)
        except (OSError, ValueError) as exc:
            raise ArtifactConflict("current generation evaluation artifacts are malformed") from exc
        if (
            artifact.dataset_sha256 != manifest.dataset_sha256
            or artifact.dataset_sha256 != dataset_sha256(dataset_path)
        ):
            raise ArtifactConflict("generation evaluation dataset checksum is inconsistent")
        if artifact.corpus_snapshot_sha256 != manifest.corpus_snapshot_sha256:
            raise ArtifactConflict("generation evaluation corpus snapshot is inconsistent")
        if artifact.case_ids != [case.id for case in cases]:
            raise ArtifactConflict("generation evaluation case coverage is inconsistent")
        return artifact, cases

    def _audit_available(self, artifact: GenerationArtifact) -> bool:
        try:
            with self.database.transaction() as connection:
                row = connection.execute(
                    "SELECT id FROM public.generation_evaluation_run WHERE id=%s",
                    (artifact.evaluation_run_id,),
                ).fetchone()
            return row is not None
        except Exception:
            return False

    def _chunks(self, ids: set[str]) -> tuple[dict[str, dict[str, Any]], bool]:
        if not ids:
            return {}, True
        try:
            with self.database.transaction() as connection:
                rows = connection.execute(
                    "SELECT gd.chunk_id,gd.corpus_version_id,gd.text_content,gd.citation_handle,"
                    "gd.item,gd.provenance,c.ticker,f.accession,f.source_url "
                    "FROM gold.search_document gd JOIN public.company c ON c.id=gd.company_id "
                    "JOIN silver.filing f ON f.id=gd.filing_id WHERE gd.chunk_id=ANY(%s)",
                    (sorted(ids),),
                ).fetchall()
            return {str(row["chunk_id"]): dict(row) for row in rows}, len(rows) == len(ids)
        except Exception:
            return {}, False

    @staticmethod
    def _cost(artifact: GenerationArtifact, prompt: PromptEvaluation, *, judge: bool) -> str | None:
        operations: list[dict[str, Any]] = []
        for case in prompt.cases:
            usage = case.judge_usage if judge else case.generation_usage
            if usage is None:
                return None
            operations.append(
                {
                    "model": artifact.judge_model if judge else artifact.generation_model,
                    **usage.model_dump(),
                }
            )
        availability, value = estimate_charge(artifact.pricing_snapshot, operations)
        if availability != "available" or value is None or not prompt.cases:
            return None
        return format(Decimal(value) / len(prompt.cases), "f")

    @staticmethod
    def _prompt_rows(artifact: GenerationArtifact) -> list[dict[str, Any]]:
        ranked = sorted(
            artifact.prompts,
            key=lambda row: (
                not bool(row.eligible),
                -float(row.mean_score or 0),
                -int(row.relevant_count or 0),
                row.median_latency,
                row.prompt_id,
            ),
        )
        output = []
        for rank, prompt in enumerate(ranked, 1):
            labels = Counter(prompt.labels)
            output.append(
                {
                    "id": prompt.prompt_id,
                    "official_rank": rank,
                    "selected": prompt.prompt_id == artifact.selected_prompt_id,
                    "eligible": bool(prompt.eligible),
                    "mean_score": prompt.mean_score,
                    "relevant_count": labels["RELEVANT"],
                    "partly_relevant_count": labels["PARTLY_RELEVANT"],
                    "non_relevant_count": labels["NON_RELEVANT"],
                    "failures": prompt.failures,
                    "valid_citation_handles": prompt.valid_citation_handles,
                    "citation_handles": prompt.citation_handles,
                    "cross_corpus_citations": prompt.cross_corpus_citations,
                    "median_latency_ms": None
                    if not prompt.generation_latencies_ms
                    else median(prompt.generation_latencies_ms),
                    "generation_cost_per_answer_usd": GenerationEvaluationDashboardService._cost(
                        artifact, prompt, judge=False
                    ),
                    "judge_cost_per_answer_usd": GenerationEvaluationDashboardService._cost(
                        artifact, prompt, judge=True
                    ),
                }
            )
        return output

    def summary(self) -> GenerationEvaluationSummary:
        artifact, cases = self._load()
        audit_available = self._audit_available(artifact)
        referenced = {
            chunk
            for prompt in artifact.prompts
            for case in prompt.cases
            for chunk in case.retrieved_chunk_ids
        } | {chunk for case in cases for chunk in case.relevant_chunk_ids}
        _, evidence_available = self._chunks(referenced)
        warnings: list[dict[str, Any]] = []
        if not audit_available:
            warnings.append(
                _recovery_warning(
                    "audit_record_unavailable",
                    "The artifact is available, but this deployment has no matching evaluation audit record.",
                )
            )
        if not evidence_available:
            warnings.append(
                _recovery_warning(
                    "evidence_unavailable",
                    "Generated answers remain reviewable, but filing evidence is incomplete or unavailable in this deployment.",
                )
            )
        try:
            config = load_generation_configuration(self.settings.generation_config_path)
            promoted_prompt_id = config.promoted_prompt_id
        except (OSError, ValueError):
            promoted_prompt_id = None
            warnings.append(
                _recovery_warning(
                    "generation_configuration_unavailable",
                    "The runtime generation configuration is unavailable, so promotion status cannot be reconciled.",
                )
            )
        prompt_rows = self._prompt_rows(artifact)
        for row in prompt_rows:
            row["promoted"] = row["id"] == promoted_prompt_id
        return GenerationEvaluationSummary(
            run={
                "id": str(artifact.evaluation_run_id),
                "status": artifact.status,
                "started_at": artifact.started_at,
                "finished_at": artifact.finished_at,
                "question_count": len(cases),
                "prompt_count": len(artifact.prompts),
                "generation_model": artifact.generation_model,
                "judge_model": artifact.judge_model,
            },
            selected_prompt_id=artifact.selected_prompt_id,
            promoted_prompt_id=promoted_prompt_id,
            prompts=prompt_rows,
            availability={
                "artifact_loaded": True,
                "audit_record_available": audit_available,
                "evidence_available": evidence_available,
            },
            warnings=warnings,
            lineage={
                "dataset_sha256": artifact.dataset_sha256,
                "corpus_snapshot_sha256": artifact.corpus_snapshot_sha256,
                "retrieval_configuration_sha256": artifact.retrieval_configuration_sha256,
                "generation_configuration_sha256": artifact.generation_configuration_sha256,
                "judge_rubric_sha256": artifact.judge_rubric_sha256,
            },
        )

    def cases(self) -> GenerationEvaluationCases:
        artifact, cases = self._load()
        by_prompt = {
            prompt.prompt_id: {case.case_id: case for case in prompt.cases}
            for prompt in artifact.prompts
        }
        output = []
        for case in cases:
            results = []
            for prompt in artifact.prompts:
                result = by_prompt[prompt.prompt_id][case.id]
                results.append(
                    {
                        "prompt_id": prompt.prompt_id,
                        "label": result.judge.label if result.judge else None,
                        "failure": result.failure,
                        "citations_valid": result.citation_audit.citation_handles
                        == result.citation_audit.valid_citation_handles
                        and result.citation_audit.cross_corpus_citations == 0,
                        "latency_ms": result.generation_latency_ms,
                    }
                )
            output.append(
                {
                    "id": case.id,
                    "question": case.question,
                    "ticker": case.ticker,
                    "items": sorted(case.allowed_items),
                    "goal": case.goal,
                    "query_type": case.query_type,
                    "results": results,
                }
            )
        return GenerationEvaluationCases(
            cases=output,
            facets={
                "tickers": sorted({case.ticker for case in cases}),
                "items": sorted({item for case in cases for item in case.allowed_items}),
                "goals": sorted({case.goal for case in cases}),
                "query_types": sorted({case.query_type for case in cases}),
            },
            warnings=[],
        )

    @staticmethod
    def _chunk(row: dict[str, Any] | None, chunk_id: str, **extra: Any) -> dict[str, Any]:
        if row is None:
            return {
                "chunk_id": chunk_id,
                "missing": True,
                "preview": "Evidence unavailable",
                **extra,
            }
        return {
            "chunk_id": chunk_id,
            "missing": False,
            "preview": preview(str(row["text_content"])),
            "citation": row["citation_handle"],
            "ticker": row["ticker"],
            "item": row["item"],
            "accession": row["accession"],
            "source_url": row["source_url"],
            **extra,
        }

    def question(self, case_id: str) -> GenerationEvaluationQuestion:
        artifact, cases = self._load()
        case = next((item for item in cases if item.id == case_id), None)
        if case is None:
            raise ArtifactMissing("unknown current generation evaluation question")
        prompt_results = []
        retrieved_ids: list[str] = []
        for prompt in artifact.prompts:
            result = next(item for item in prompt.cases if item.case_id == case_id)
            if not retrieved_ids:
                retrieved_ids = result.retrieved_chunk_ids
            prompt_results.append({"prompt_id": prompt.prompt_id, **result.model_dump(mode="json")})
        ids = set(retrieved_ids) | set(case.relevant_chunk_ids)
        chunks, complete = self._chunks(ids)
        warnings = (
            []
            if complete
            else [
                _recovery_warning(
                    "evidence_unavailable",
                    "Evidence is incomplete or unavailable in this deployment.",
                )
            ]
        )
        return GenerationEvaluationQuestion(
            question={
                "id": case.id,
                "question": case.question,
                "ticker": case.ticker,
                "items": sorted(case.allowed_items),
                "goal": case.goal,
                "query_type": case.query_type,
                "accession": case.accession,
            },
            results=prompt_results,
            expected=[
                self._chunk(chunks.get(chunk), chunk, matched=True)
                for chunk in sorted(case.relevant_chunk_ids)
            ],
            retrieved=[
                self._chunk(
                    chunks.get(chunk), chunk, rank=index, matched=chunk in case.relevant_chunk_ids
                )
                for index, chunk in enumerate(retrieved_ids, 1)
            ],
            evidence_available=complete,
            warnings=warnings,
        )

    def prompt(self, prompt_id: str) -> GenerationPromptSource:
        artifact, _ = self._load()
        evaluated = next((item for item in artifact.prompts if item.prompt_id == prompt_id), None)
        if evaluated is None:
            raise ArtifactMissing("unknown current generation evaluation prompt")
        try:
            source, current_hash = load_generation_configuration(
                self.settings.generation_config_path
            ).prompt(prompt_id)
        except (OSError, ValueError) as exc:
            raise ArtifactMissing("evaluated prompt source is unavailable") from exc
        if current_hash != evaluated.prompt_sha256:
            raise ArtifactConflict("current prompt source does not match the evaluated artifact")
        return GenerationPromptSource(
            prompt_id=prompt_id, prompt_sha256=current_hash, source=source
        )

    def chunk(self, chunk_id: str) -> GenerationEvaluationChunk:
        artifact, cases = self._load()
        allowed = {chunk for case in cases for chunk in case.relevant_chunk_ids} | {
            chunk
            for prompt in artifact.prompts
            for case in prompt.cases
            for chunk in case.retrieved_chunk_ids
        }
        if chunk_id not in allowed:
            raise ArtifactMissing("chunk is not referenced by the current generation evaluation")
        row = self._chunks({chunk_id})[0].get(chunk_id)
        if row is None:
            raise ArtifactMissing("referenced chunk is unavailable in this deployment")
        return GenerationEvaluationChunk(
            chunk_id=chunk_id,
            corpus_version_id=str(row["corpus_version_id"]),
            text=str(row["text_content"]),
            preview=preview(str(row["text_content"])),
            citation=str(row["citation_handle"]),
            ticker=str(row["ticker"]),
            item=str(row["item"]),
            accession=str(row["accession"]),
            source_url=str(row["source_url"]),
            provenance=dict(row["provenance"]),
        )
