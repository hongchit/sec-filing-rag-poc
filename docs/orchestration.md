# Orchestration

Kestra coordinates ingestion but does not own filing policy or corpus state. Public requests ask
FastAPI to persist and submit a batch. Scheduled and Kestra-UI requests use
`scheduled_filing_launcher`, which asks FastAPI to persist the batch and then invokes the same
`sec_filings.ingestion.filing_batch` processing flow. Every callback reloads authoritative state by
UUID.

## Component boundary

```mermaid
---
title: Ingestion entry paths converge on one processing flow
---
flowchart TD
  UI[Authenticated browser] -->|public batch request| API[FastAPI]
  CRON[Daily 06:08 UTC trigger] --> L[scheduled_filing_launcher]
  KUI[Manual Kestra UI run] --> L
  L -->|protected create request| API
  API -->|persist batch and items| DB[(Application PostgreSQL)]
  API -->|public path: batch_id| B[filing_batch]
  L -->|scheduled or UI path: batch_id| B
  B -->|reference-only callbacks| API
  API -->|state transitions| DB
```

This reference-only boundary keeps filing bytes, provider objects, model payloads, and business
credentials out of workflow transport. Kestra supplies scheduling, retries, sequential iteration,
execution history, local error handling, and unconditional finalization. Python supplies selection,
validation, idempotency, persistence, activation, and failure policy.

## Scheduled launcher sequence

The launcher definition is `workflows/scheduled_filing_launcher.yaml`. Its schedule uses
`8 6 * * *` in `Etc/UTC`, recovers only the last missed run, and disallows overlapping scheduled
executions. Optional launcher inputs support an ordered ticker subset or exact fiscal year for a
manual Kestra-UI execution; the daily trigger omits both to request every enabled company's latest
original 10-K.

```mermaid
---
title: Scheduled ingestion request and processing sequence
---
sequenceDiagram
  participant S as Kestra launcher
  participant B as Kestra filing_batch
  participant A as FastAPI
  participant D as Application PostgreSQL
  participant E as SEC
  participant O as OpenAI embeddings
  S->>A: POST scheduled-filing-batches + launcher execution ID
  A->>D: Resolve first admin and atomically persist batch/items
  D-->>A: batch_id
  A-->>S: Safe created-batch metadata
  S->>B: Subflow(batch_id)
  loop One enabled company at a time
    B->>A: Select and acquire filing by item UUID
    A->>E: Discover latest and acquire selected HTML
    E-->>A: Filing metadata and HTML
    B->>A: Process persisted acquisition
    alt Ready accession and compatibility key already exist
      A->>D: Record unchanged skipped run
      Note over A,O: No OpenAI request
    else New or incompatible corpus
      A->>O: Create chunk embeddings
      O-->>A: Vectors and usage
      A->>D: Persist and conditionally activate corpus
    end
  end
  B->>A: Finalize batch
  B-->>S: Child execution state
```

```mermaid
---
title: Scheduled ingestion responsibility swimlanes
---
flowchart TD
  subgraph KL[Kestra launcher lane]
    T[Evaluate daily schedule] --> C[Request batch creation]
    C --> SF[Start and await filing_batch]
  end
  subgraph AP[FastAPI policy lane]
    O[Resolve owner and validate intent] --> P[Select acquire parse and decide reuse]
  end
  subgraph DB[Application PostgreSQL lane]
    PB[Persist batch and ordered items] --> PS[Persist lifecycle corpus and usage]
  end
  subgraph KP[Kestra processing lane]
    IT[Iterate sequentially] --> RT[Retry and isolate item failures]
    RT --> F[Finalize unconditionally]
  end
  C --> O
  O --> PB
  PB --> SF
  SF --> IT
  IT --> P
  P --> PS
  P --> SEC[SEC source system]
  P -. only for new or incompatible corpus .-> AI[OpenAI embeddings]
  F --> PS
```

FastAPI attributes scheduled preparation cost to the first address in `GOOGLE_ADMIN_EMAILS`. That
administrator must have signed in once and remain active; otherwise batch creation fails before
reserving cost or writing a batch.

## Flow graph

```mermaid
---
title: Filing batch workflow
---
flowchart TD
  S[Receive batch_id] --> L[Load persisted item IDs]
  L --> F{For each item<br/>concurrency 1}
  F --> SE[Select filing]
  SE -->|selected| AC[Acquire source]
  AC --> PR[Process corpus reference]
  SE -->|exact year absent| SK[Item already skipped]
  SE -. error .-> ER[Failure callback]
  AC -. error .-> ER
  PR -. error .-> ER
  SK --> N[Next item]
  ER --> N
  PR --> N
  N --> F
  F -->|all visited| FI[Finally: finalize batch]
```

The flow definition is `workflows/filing_batch.yaml`. `ForEach` uses `concurrencyLimit: 1` to make
SEC access and state transitions easy to inspect. Local errors call the item-failure endpoint with
`allowFailure: true`, so later companies continue. The flow-level `finally` callback runs regardless
of earlier task outcomes.

## State machines

```mermaid
---
title: Filing batch item states
---
stateDiagram-v2
  [*] --> pending
  pending --> selecting
  selecting --> acquiring: eligible filing
  selecting --> skipped: exact year absent
  acquiring --> processing
  processing --> succeeded
  selecting --> failed
  acquiring --> failed
  processing --> failed
```

Items normally move `pending → selecting → acquiring → processing → succeeded`. `skipped` and
`failed` are terminal. Each transition records references, timestamps, execution correlation, and a
bounded safe error where applicable.

```mermaid
---
title: Filing batch states
---
stateDiagram-v2
  [*] --> submitted
  submitted --> running
  submitted --> failed: Kestra submission fails
  running --> succeeded: all succeeded
  running --> partial_failure: success plus non-success
  running --> failed: no successes
```

Finalization marks stranded non-terminal items failed before calculating the aggregate. In latest
mode, an unchanged compatible corpus is a healthy completion: all-unchanged and mixed
new-plus-unchanged batches end `succeeded` unless an item failed. In exact-year mode, skipped items
still mean the requested filing was absent and do not count as success.

## Retry and idempotency

Selection, acquisition, processing, failure, and finalization are designed for safe repetition.
Kestra applies constant retry to callback tasks. Application safeguards include:

- terminal filing selection is reused;
- a unique launcher execution ID returns the already-created batch after an HTTP retry;
- an acquisition is identified by company, accession, and checksum;
- a corpus is identified by filing plus compatibility key;
- ready compatible corpora are reused rather than re-embedded;
- failure and finalization callbacks tolerate already-terminal state;
- candidate persistence and active-pointer changes are transactional.

Latest processing can promote a compatible ready historical corpus. Exact-year processing never
promotes. The detailed source and activation logic belongs to [Pipeline](pipeline.md).

## Authentication and failures

FastAPI authenticates to Kestra with Basic authentication. Kestra resolves the base64-encoded
internal bearer token from its secret environment and uses it for callbacks. Error messages never
include either credential.

If submission fails, FastAPI marks pending items failed because no workflow can visit them. If an
individual task exhausts retries, its local callback terminates only that item. Finalization is the
last safety net for interrupted executions. Operators diagnose application policy in FastAPI logs,
task attempts in Kestra, and durable outcomes in application tables; see
[Troubleshooting](troubleshooting.md).

For the scheduled path, failure to create a batch leaves no application work. If batch creation
succeeds but the processing subflow cannot start after retries, the launch-failure callback marks
the batch and pending items failed and reconciles the unused reservation.

![Kestra execution: The `filing_batch` task graph with sequential item processing, one locally handled failure, and the finalization task.](assets/screenshots/801%20-%20Kestra%20-%20filing_batch%20-%20execution.png)
