# ADR 0004: Benchmark-selected retrieval configuration

## Status

Accepted

## Context

Keyword and semantic retrieval fail differently. Selecting a strategy from intuition or a few demo
questions can hide systematic misses, and model-generated questions alone do not constitute reliable
ground truth.

## Decision

Promote retrieval defaults only through a checksum-bound benchmark of human-reviewed questions and
relevant chunk IDs. Compare keyword BM25, vector, weighted hybrid, and reciprocal-rank-fusion
configurations under the same cases. Select deterministically by MRR, then Hit Rate, median latency,
and stable strategy order. Record corpus, dataset, configuration, model, and result lineage.

## Consequences

- The selected default has measurable evidence and reproducible inputs.
- Coverage, misses, and later hits remain inspectable rather than hidden by one average.
- Corpus, chunking, embeddings, scoring, or reviewed-case changes require a rerun.
- Human review adds time but prevents generated labels from becoming unquestioned truth.
- Benchmark success applies to the measured domain and is not a universal performance guarantee.

## Alternatives considered

- Use vector retrieval by convention: rejected because exact filing terms remain important.
- Select on Hit Rate alone: rejected because rank position affects evidence quality and prompt use.
- Let the model generate and approve its own benchmark: rejected because it removes independent
  review and can reward its own wording patterns.
