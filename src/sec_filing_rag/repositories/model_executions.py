from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..core.pricing import PricingConfiguration, estimate_charge
from .database import Database


class ModelExecutionRepository:
    """Read-only operational accounting across evaluation execution families."""

    def __init__(self, database: Database, pricing: PricingConfiguration) -> None:
        self.database = database
        self.pricing = pricing

    def list(self, *, limit: int, offset: int) -> dict[str, Any]:
        union = (
            "SELECT 'retrieval_evaluation' AS run_type,id,status::text,safe_error,started_at,finished_at,"
            "pricing_snapshot,NULL::text[] AS declared_models FROM public.retrieval_evaluation_run UNION ALL "
            "SELECT 'generation_evaluation',id,status::text,safe_error,started_at,finished_at,"
            "pricing_snapshot,ARRAY[chat_model,judge_model] FROM public.generation_evaluation_run UNION ALL "
            "SELECT 'ground_truth_generation',id,status::text,safe_error,started_at,finished_at,"
            "pricing_snapshot,ARRAY[model] FROM public.ground_truth_generation_run"
        )
        with self.database.transaction() as connection:
            total = connection.execute(
                f"SELECT count(*) AS count FROM ({union}) executions"
            ).fetchone()
            runs = connection.execute(
                f"SELECT * FROM ({union}) executions ORDER BY started_at DESC,id DESC LIMIT %s OFFSET %s",
                (limit, offset),
            ).fetchall()
            items = []
            for run in runs:
                owner_column = {
                    "retrieval_evaluation": "evaluation_run_id",
                    "generation_evaluation": "generation_evaluation_run_id",
                    "ground_truth_generation": "ground_truth_generation_run_id",
                }[run["run_type"]]
                usage = connection.execute(
                    "SELECT operation,model,input_tokens,output_tokens,total_tokens,latency_ms,"
                    "usage_status::text AS usage_status,normalized_status,attempt,retry_count,"
                    "provider_started_at,provider_finished_at FROM public.llm_usage WHERE "
                    + owner_column
                    + "=%s ORDER BY id",
                    (run["id"],),
                ).fetchall()
                items.append(self._summarize(dict(run), [dict(value) for value in usage]))
        count = int(total["count"] if total else 0)
        return {
            "items": items,
            "total": count,
            "limit": limit,
            "offset": offset,
            "next_offset": offset + limit if offset + limit < count else None,
        }

    def _summarize(
        self, run: dict[str, Any], operations: Sequence[dict[str, Any]]
    ) -> dict[str, Any]:
        stored_snapshot = run.pop("pricing_snapshot")
        declared_models = run.pop("declared_models") or []
        snapshot = stored_snapshot or {
            "version": self.pricing.version,
            "sha256": self.pricing.sha256(),
            "currency": self.pricing.currency,
            "token_unit": self.pricing.token_unit,
            "models": {
                model: price.model_dump(mode="json") for model, price in self.pricing.models.items()
            },
        }
        availability, estimate = estimate_charge(snapshot, list(operations))
        known_inputs = [value["input_tokens"] for value in operations]
        known_outputs = [value["output_tokens"] for value in operations]
        known_totals = [value["total_tokens"] for value in operations]
        return {
            **run,
            "models": sorted(
                {str(model) for model in declared_models}
                | {value["model"] for value in operations}
                | (set(snapshot["models"]) if stored_snapshot else set())
            ),
            "operations": operations,
            "provider_calls": len(operations),
            "retries": sum(int(value["retry_count"]) for value in operations),
            "failures": len([value for value in operations if value["usage_status"] == "failed"]),
            "input_tokens": sum(value for value in known_inputs if value is not None),
            "output_tokens": sum(value for value in known_outputs if value is not None),
            "total_tokens": sum(value for value in known_totals if value is not None),
            "usage_available": availability == "available",
            "estimate_status": availability,
            "estimated_usd": estimate,
            "pricing_basis": "stored_snapshot" if stored_snapshot else "current_price_estimate",
            "pricing_version": snapshot.get("version"),
            "pricing_sha256": snapshot.get("sha256"),
        }
