from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

JudgeLabel = Literal["RELEVANT", "PARTLY_RELEVANT", "NON_RELEVANT"]
LABEL_SCORE: dict[JudgeLabel, int] = {
    "RELEVANT": 2,
    "PARTLY_RELEVANT": 1,
    "NON_RELEVANT": 0,
}


class JudgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: JudgeLabel
    explanation: str = Field(min_length=1, max_length=2000)


class PromptEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_id: str
    labels: list[JudgeLabel]
    valid_citation_handles: int = Field(ge=0)
    citation_handles: int = Field(ge=0)
    cross_corpus_citations: int = Field(ge=0)
    failures: int = Field(ge=0)
    generation_latencies_ms: list[int]

    @field_validator("generation_latencies_ms")
    @classmethod
    def nonnegative_latencies(cls, values: list[int]) -> list[int]:
        if any(value < 0 for value in values):
            raise ValueError("latencies must be nonnegative")
        return values

    @property
    def eligible(self) -> bool:
        return (
            self.citation_handles > 0
            and self.valid_citation_handles == self.citation_handles
            and self.cross_corpus_citations == 0
        )

    @property
    def mean_score(self) -> float:
        return (
            sum(LABEL_SCORE[label] for label in self.labels) / len(self.labels)
            if self.labels
            else 0
        )

    @property
    def relevant_count(self) -> int:
        return self.labels.count("RELEVANT")

    @property
    def median_latency(self) -> float:
        return (
            median(self.generation_latencies_ms) if self.generation_latencies_ms else float("inf")
        )


def select_generation_winner(rows: list[PromptEvaluation]) -> PromptEvaluation:
    eligible = [row for row in rows if row.eligible]
    if not eligible:
        raise ValueError("no prompt passed deterministic citation guardrails")
    return sorted(
        eligible,
        key=lambda row: (
            -row.mean_score,
            -row.relevant_count,
            row.failures,
            row.median_latency,
            row.prompt_id,
        ),
    )[0]


class GenerationArtifact(BaseModel):
    """Strict envelope used for reproducible JSON generation-evaluation artifacts."""

    model_config = ConfigDict(extra="forbid")
    version: str
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieval_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_model: str
    judge_model: str
    cases: list[dict[str, Any]]
    prompts: list[PromptEvaluation]
    selected_prompt_id: str


def load_generation_artifact(path: Path) -> GenerationArtifact:
    return GenerationArtifact.model_validate_json(path.read_text(encoding="utf-8"))


def artifact_markdown(artifact: GenerationArtifact) -> str:
    rows = [
        "# Generation evaluation",
        "",
        f"Cases: {len(artifact.cases)}",
        "",
        "| Prompt | Mean | Relevant | Failures | Eligible |",
        "|---|---:|---:|---:|:---:|",
    ]
    for prompt in artifact.prompts:
        rows.append(
            f"| `{prompt.prompt_id}` | {prompt.mean_score:.4f} | {prompt.relevant_count} | {prompt.failures} | {'yes' if prompt.eligible else 'no'} |"
        )
    rows.extend(["", f"Promoted prompt: `{artifact.selected_prompt_id}`", ""])
    return "\n".join(rows)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
