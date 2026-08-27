from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from ..core.pricing import estimate_charge
from ..generation.service import (
    INVESTMENT_ADVICE_MESSAGE,
    OUT_OF_SCOPE_MESSAGE,
    GeneratedAnswer,
    IdempotencyConflict,
    ProviderUsage,
    ResearchInProgress,
    ResearchRequest,
)
from ..retrieval.service import RetrievalResult
from .database import Database


class ResearchRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def idempotent_result(self, key: uuid.UUID, request: ResearchRequest) -> dict[str, Any] | None:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT id,ticker,corpus_version_id,goal,question,allowed_items,status "
                "FROM public.research_request WHERE idempotency_key=%s",
                (key,),
            ).fetchone()
        if row is None:
            return None
        expected = (
            request.ticker,
            request.corpus_version_id,
            request.goal,
            request.question,
            sorted(request.allowed_items) if request.allowed_items else None,
        )
        actual = (
            row["ticker"],
            row["corpus_version_id"],
            row["goal"],
            row["question"],
            row["allowed_items"],
        )
        if actual != expected:
            raise IdempotencyConflict("idempotency key was used with different inputs")
        if row["status"] == "running":
            raise ResearchInProgress(row["id"])
        value = self.get(row["id"])
        if value is None:
            raise RuntimeError("persisted idempotent research disappeared")
        return value

    def create(
        self,
        request: ResearchRequest,
        *,
        prompt_id: str,
        model: str,
        idempotency_key: uuid.UUID | None = None,
        retrieval_configuration_sha256: str | None = None,
        generation_configuration_sha256: str | None = None,
        prompt_sha256: str | None = None,
        pricing_snapshot: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        research_id = uuid.uuid4()
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT c.id AS company_id,f.accession FROM silver.corpus_version cv "
                "JOIN silver.filing f ON f.id=cv.filing_id JOIN public.company c ON c.id=f.company_id "
                "WHERE cv.id=%s AND cv.status='ready' AND c.enabled AND c.ticker=%s",
                (request.corpus_version_id, request.ticker),
            ).fetchone()
            if row is None:
                raise ValueError("unknown company, non-ready corpus, or corpus/company mismatch")
            connection.execute(
                "INSERT INTO public.research_request(id,company_id,corpus_version_id,ticker,goal,question,allowed_items,status,prompt_id,chat_model,idempotency_key,retrieval_configuration_sha256,generation_configuration_sha256,prompt_sha256,accession,pricing_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'running',%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    research_id,
                    row["company_id"],
                    request.corpus_version_id,
                    request.ticker,
                    request.goal,
                    request.question,
                    sorted(request.allowed_items) if request.allowed_items else None,
                    prompt_id,
                    model,
                    idempotency_key,
                    retrieval_configuration_sha256,
                    generation_configuration_sha256,
                    prompt_sha256,
                    row["accession"],
                    json.dumps(pricing_snapshot) if pricing_snapshot is not None else None,
                ),
            )
        return research_id

    def identity(self, research_id: uuid.UUID) -> tuple[str, str]:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT rr.ticker,f.accession FROM public.research_request rr "
                "JOIN silver.corpus_version cv ON cv.id=rr.corpus_version_id "
                "JOIN silver.filing f ON f.id=cv.filing_id WHERE rr.id=%s",
                (research_id,),
            ).fetchone()
        if row is None:
            raise ValueError("research request disappeared")
        return row["ticker"], row["accession"]

    def save_evidence(self, research_id: uuid.UUID, evidence: list[RetrievalResult]) -> None:
        with self.database.transaction() as connection:
            for item in evidence:
                connection.execute(
                    "INSERT INTO public.research_evidence(research_id,rank,chunk_id,strategy,score,citation_handle,ticker,accession,item,provenance) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        research_id,
                        item.rank,
                        item.chunk_id,
                        item.strategy,
                        item.score,
                        item.citation_handle,
                        item.ticker,
                        item.accession,
                        item.item,
                        json.dumps(item.provenance),
                    ),
                )

    def usage(self, research_id: uuid.UUID, **values: Any) -> None:
        usage: ProviderUsage = values["usage"]
        usage_status = "reported" if usage.total_tokens is not None else "unavailable"
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO public.llm_usage(research_id,operation,model,input_tokens,output_tokens,total_tokens,latency_ms,usage_status,normalized_status,attempt,retry_count,provider_started_at,provider_finished_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    research_id,
                    values["operation"],
                    values["model"],
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.total_tokens,
                    values["latency_ms"],
                    usage_status,
                    values["outcome"],
                    values["attempt"],
                    values["attempt"] - 1,
                    datetime.fromtimestamp(values["started_at"], UTC),
                    datetime.fromtimestamp(values["finished_at"], UTC),
                ),
            )

    def succeed(self, research_id: uuid.UUID, answer: GeneratedAnswer) -> dict[str, Any]:
        rejection_message = (
            INVESTMENT_ADVICE_MESSAGE
            if answer.disposition == "investment_advice"
            else OUT_OF_SCOPE_MESSAGE
            if answer.disposition == "out_of_scope"
            else None
        )
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE public.research_request SET status='succeeded',finished_at=now() WHERE id=%s",
                (research_id,),
            )
            connection.execute(
                "INSERT INTO public.research_result(research_id,answer,insufficient_evidence,limitations,policy_refusal,disposition,rejection_message) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    research_id,
                    json.dumps([item.model_dump(mode="json") for item in answer.paragraphs]),
                    answer.insufficient_evidence,
                    json.dumps(answer.limitations),
                    answer.policy_refusal,
                    answer.disposition,
                    rejection_message,
                ),
            )
        value = self.get(research_id)
        if value is None:
            raise RuntimeError("persisted research result was not found")
        return value

    def fail(self, research_id: uuid.UUID, error: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE public.research_request SET status='failed',safe_error=%s,finished_at=now() WHERE id=%s",
                (error, research_id),
            )

    def get(self, research_id: uuid.UUID) -> dict[str, Any] | None:
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT rr.id AS research_id,rr.ticker,rr.corpus_version_id,rr.goal,rr.question,rr.allowed_items,rr.status,rr.prompt_id,rr.chat_model,rr.safe_error,rr.created_at,rr.finished_at,rr.accession,rr.retrieval_configuration_sha256,rr.generation_configuration_sha256,rr.prompt_sha256,rr.pricing_snapshot,res.answer,res.limitations,res.insufficient_evidence,res.policy_refusal,res.disposition,res.rejection_message "
                "FROM public.research_request rr LEFT JOIN public.research_result res ON res.research_id=rr.id WHERE rr.id=%s",
                (research_id,),
            ).fetchone()
            if row is None:
                return None
            evidence = connection.execute(
                "SELECT re.rank,re.chunk_id,re.strategy,re.score,ch.citation_handle,c.ticker,f.accession,s.item,ch.text_content AS excerpt,ch.source_start,ch.source_end,s.source_anchor,f.source_url "
                "FROM public.research_evidence re JOIN silver.chunk ch ON ch.id=re.chunk_id "
                "JOIN silver.section s ON s.id=ch.section_id JOIN silver.corpus_version cv ON cv.id=ch.corpus_version_id "
                "JOIN silver.filing f ON f.id=cv.filing_id JOIN public.company c ON c.id=f.company_id "
                "WHERE re.research_id=%s ORDER BY re.rank",
                (research_id,),
            ).fetchall()
            operations = connection.execute(
                "SELECT operation,model,input_tokens,output_tokens,total_tokens,latency_ms,usage_status,normalized_status,attempt,retry_count,provider_started_at,provider_finished_at "
                "FROM public.llm_usage WHERE research_id=%s ORDER BY id",
                (research_id,),
            ).fetchall()
        value = dict(row)
        value["evidence"] = [dict(item) for item in evidence]
        op_values = [dict(item) for item in operations]
        embedding = [
            item["input_tokens"] for item in op_values if item["operation"] == "query_embedding"
        ]
        answer_in = [
            item["input_tokens"] for item in op_values if item["operation"] == "answer_generation"
        ]
        answer_out = [
            item["output_tokens"] for item in op_values if item["operation"] == "answer_generation"
        ]
        totals = [item["total_tokens"] for item in op_values]
        value["usage"] = {
            "query_embedding_input": sum(embedding)
            if embedding and all(x is not None for x in embedding)
            else None,
            "answer_generation_input": sum(answer_in)
            if answer_in and all(x is not None for x in answer_in)
            else None,
            "answer_generation_output": sum(answer_out)
            if answer_out and all(x is not None for x in answer_out)
            else None,
            "complete_request_total": sum(totals)
            if totals and all(x is not None for x in totals)
            else None,
            "provider_calls": len(op_values),
        }
        pricing_snapshot = value.pop("pricing_snapshot")
        estimate_status, estimated_charge = estimate_charge(pricing_snapshot, op_values)
        value["estimate_status"] = estimate_status
        value["estimated_charge_usd"] = estimated_charge
        if value.get("disposition") in ("investment_advice", "out_of_scope"):
            value["answer"] = []
            value["limitations"] = []
            value["evidence"] = []
        strategy = value["evidence"][0]["strategy"] if value["evidence"] else None
        value["run_details"] = {
            "accession": value.pop("accession"),
            "corpus_version_id": value["corpus_version_id"],
            "retrieval_configuration_sha256": value.pop("retrieval_configuration_sha256"),
            "generation_configuration_sha256": value.pop("generation_configuration_sha256"),
            "prompt_sha256": value.pop("prompt_sha256"),
            "prompt_id": value["prompt_id"],
            "chat_model": value["chat_model"],
            "strategy": strategy,
            "alpha": 0.25 if strategy == "weighted_hybrid" else None,
            "evidence_count": len(value["evidence"]),
            "attempts": max(
                (item["attempt"] for item in op_values if item["operation"] == "answer_generation"),
                default=0,
            ),
            "latency_ms": sum(
                item["latency_ms"] for item in op_values if item["latency_ms"] is not None
            )
            or None,
            "operations": op_values,
            "pricing_version": pricing_snapshot.get("version") if pricing_snapshot else None,
            "pricing_sha256": pricing_snapshot.get("sha256") if pricing_snapshot else None,
        }
        return value

    def history(
        self, *, limit: int, cursor: tuple[datetime, uuid.UUID] | None
    ) -> list[dict[str, Any]]:
        with self.database.transaction() as connection:
            if cursor is None:
                rows = connection.execute(
                    "SELECT id FROM public.research_request ORDER BY created_at DESC,id DESC LIMIT %s",
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT id FROM public.research_request WHERE (created_at,id)<(%s,%s) ORDER BY created_at DESC,id DESC LIMIT %s",
                    (cursor[0], cursor[1], limit),
                ).fetchall()
        return [value for row in rows if (value := self.get(row["id"])) is not None]

    def save_feedback(
        self, research_id: uuid.UUID, rating: str, comment: str | None
    ) -> dict[str, Any]:
        feedback_id = uuid.uuid4()
        with self.database.transaction() as connection:
            row = connection.execute(
                "INSERT INTO public.feedback(id,research_id,rating,comment) VALUES (%s,%s,%s,%s) "
                "ON CONFLICT (research_id) DO UPDATE SET rating=EXCLUDED.rating,comment=EXCLUDED.comment,updated_at=now() "
                "RETURNING id,research_id AS result_id,rating,comment,created_at,updated_at",
                (feedback_id, research_id, rating, comment),
            ).fetchone()
        value = dict(row)
        value["result_type"] = "research_answer"
        return value
