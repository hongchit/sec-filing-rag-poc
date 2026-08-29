# ADR 0002: Immutable corpus versions and explicit activation

## Status

Accepted

## Context

New filings and processing changes must not silently retarget old research or replace a usable corpus
with an incomplete candidate. Exact-year preparation is needed for evaluation and historical review
without changing ordinary retrieval.

## Decision

Represent each filing/compatibility result as an immutable corpus version. A company has at most one
active/default pointer. Latest processing may atomically move that pointer after candidate validation;
exact-year processing leaves ready data historical. Stored research, evaluation cases, and citation
links pin the corpus UUID.

## Consequences

- Historical evidence remains reproducible and directly readable.
- Failed candidates leave the previous default available.
- Compatible historical versions can be promoted without re-embedding.
- Storage grows with retained source and processing versions.
- Clients must distinguish free browsing of the active corpus from pinned historical access.

## Alternatives considered

- Update one corpus in place: rejected because it destroys lineage and invalidates old citations.
- Activate every successfully processed year: rejected because period-specific preparation would
  unexpectedly change normal research.
- Resolve stored results through the current default: rejected because evidence would drift.
