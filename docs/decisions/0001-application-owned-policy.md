# ADR 0001: Application-owned policy and reference-only orchestration

## Status

Accepted

## Context

Filing ingestion is long-running and benefits from retries, sequential company processing, execution
history, and unconditional cleanup. Placing selection, validation, and activation policy directly in
workflow YAML would split the source of truth and require large provider objects or filing content to
cross the orchestration boundary.

## Decision

FastAPI and its services own business decisions and durable application state. Kestra receives a
persisted batch UUID, loads item UUIDs, and calls protected reference-only endpoints. It does not
receive source HTML, provider objects, model payloads, or application credentials beyond the callback
token resolved from its secret environment.

## Consequences

- Application transactions and database constraints remain authoritative.
- Workflow payloads are small, replayable, and safer to log.
- Kestra can retry without reimplementing idempotency or corpus policy.
- Diagnosing a run requires correlating application and Kestra identifiers.
- FastAPI must remain available while callbacks execute.

## Alternatives considered

- Implement ingestion policy in Kestra tasks: rejected because policy and state would be split.
- Pass acquired HTML through workflow outputs: rejected because of size, security, and replay costs.
- Run ingestion synchronously inside the public request: rejected because provider and embedding work
  exceeds an appropriate request lifecycle.
