from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from openai import OpenAI

from ..domain.filings import safe_error
from ..generation.service import OpenAIAnswerProvider, ProviderUsage
from ..repositories.database import Database
from ..retrieval.service import RetrievalResult
from .generation import JudgeResult
from .service import EvaluationCase


class OpenAIJudgeProvider:
    def __init__(self, client: OpenAI) -> None:
        self.client = client

    def judge(self, *, model: str, prompt: str) -> tuple[JudgeResult, ProviderUsage]:
        response = self.client.responses.parse(model=model, input=prompt, text_format=JudgeResult)
        if response.output_parsed is None:
            raise ValueError("judge returned no structured verdict")
        usage = getattr(response, "usage", None)
        return response.output_parsed, ProviderUsage(
            getattr(usage, "input_tokens", None),
            getattr(usage, "output_tokens", None),
            getattr(usage, "total_tokens", None),
        )


class DatabaseGenerationEvaluationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_run(self, **values: Any) -> uuid.UUID:
        run_id = uuid.uuid4()
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO public.generation_evaluation_run(id,dataset_sha256,corpus_snapshot_sha256,retrieval_configuration_sha256,generation_configuration_sha256,chat_model,judge_model,pricing_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    run_id,
                    values["dataset_sha256"],
                    values["corpus_snapshot_sha256"],
                    values["retrieval_configuration_sha256"],
                    values["generation_configuration_sha256"],
                    values["chat_model"],
                    values["judge_model"],
                    json.dumps(values["pricing_snapshot"]),
                ),
            )
        return run_id

    def reference_chunks(self, case: EvaluationCase) -> list[RetrievalResult]:
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT gd.chunk_id,c.ticker,f.accession,gd.item,gd.text_content,gd.citation_handle,gd.provenance FROM gold.search_document gd JOIN public.company c ON c.id=gd.company_id JOIN silver.filing f ON f.id=gd.filing_id WHERE gd.corpus_version_id=%s AND gd.chunk_id=ANY(%s) ORDER BY gd.chunk_id",
                (case.corpus_version_id, sorted(case.relevant_chunk_ids)),
            ).fetchall()
        return [
            RetrievalResult(
                str(row["chunk_id"]),
                row["ticker"],
                row["accession"],
                row["item"],
                rank,
                "keyword",
                1.0,
                row["text_content"],
                row["citation_handle"],
                row["provenance"],
            )
            for rank, row in enumerate(rows, 1)
        ]

    def usage(self, run_id: uuid.UUID, **values: Any) -> None:
        usage = values["usage"]
        outcome = values["outcome"]
        succeeded = outcome == "succeeded"
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO public.llm_usage(generation_evaluation_run_id,operation,model,input_tokens,output_tokens,total_tokens,latency_ms,usage_status,normalized_status,attempt,retry_count,provider_started_at,provider_finished_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    run_id,
                    values["operation"],
                    values["model"],
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.total_tokens,
                    values["latency_ms"],
                    "reported" if usage.total_tokens is not None else "unavailable",
                    "succeeded" if succeeded else safe_error(outcome),
                    values.get("attempt", 1),
                    max(0, values.get("attempt", 1) - 1),
                    datetime.now(UTC),
                    datetime.now(UTC),
                ),
            )

    def finish(self, run_id: uuid.UUID, **values: Any) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE public.generation_evaluation_run SET status=%s,selected_prompt_id=%s,selection_rationale=%s,safe_error=%s,finished_at=now() WHERE id=%s",
                (
                    values["status"],
                    values["selected_prompt_id"],
                    json.dumps(values["selection_rationale"]),
                    values["safe_error"],
                    run_id,
                ),
            )


__all__ = ["DatabaseGenerationEvaluationRepository", "OpenAIAnswerProvider", "OpenAIJudgeProvider"]
