# Documentation

This index is the entry point to the system's technical documentation. Each subject has one
authoritative home; other documents provide context and link to it rather than repeating the same
rules.

## Suggested path

1. Follow [Getting started](getting-started.md) to clone, configure, ingest, evaluate, and use the
   system.
2. Read [Architecture](architecture.md) for the system model and trust boundaries.
3. Follow the four pillars: [Pipeline](pipeline.md), [Evaluation](evaluation.md),
   [Research](research.md), and [Corpus reader](corpus-reader.md).
4. Use [API](api.md), [Database schema](database-schema.md), and
   [Configuration](configuration.md) as implementation references.
5. Use [Local development](local-development.md), [Testing](testing.md),
   [Operations](operations.md), and [Troubleshooting](troubleshooting.md) while running the system.

## Documentation map

| Topic | Authoritative document | Covers |
| --- | --- | --- |
| Setup and first use | [Getting started](getting-started.md) | Prerequisites, configuration, ingestion, evaluation, promotion, acceptance |
| Commands | [Command reference](commands.md) | Application CLIs, frontend scripts, checks, and authoritative workflow links |
| System design | [Architecture](architecture.md) | Components, boundaries, layers, invariants, trust model |
| API behavior | [API](api.md) | Routes, authentication, errors, idempotency, SSE, generated contracts |
| Workflow engine | [Orchestration](orchestration.md) | Kestra graph, callbacks, retries, state transitions |
| Source processing | [Pipeline](pipeline.md) | Filing selection, acquisition, extraction, chunks, embeddings, activation |
| Retrieval quality | [Evaluation](evaluation.md) | Ground truth, strategies, metrics, selection, rerun policy |
| Retrieval learning workflow | [Ground-truth prompt and retrieval evaluation](retrieval-evaluation-workflow.md#ground-truth-question-generation-prompt) | Question-generation prompt, worked metrics, controlled benchmarking |
| Full-RAG learning workflow | [Prompt roles in full-RAG evaluation](rag-evaluation-workflow.md#prompt-roles-in-full-rag-evaluation) | Generation candidates, answer judging, calibration, failure analysis |
| Answer generation | [Research](research.md) | Retrieval-to-answer flow, grounding, policy, persistence, cost |
| Human source access | [Corpus reader](corpus-reader.md) | Reader routes, paragraphs, highlights, EDGAR links |
| Stored data | [Database schema](database-schema.md) | Tables, constraints, ownership, read models |
| Runtime settings | [Configuration](configuration.md) | Environment and tracked configuration contracts |
| Developer setup | [Local development](local-development.md) | Dev Container, ports, startup, daily commands |
| Verification | [Testing](testing.md) | Test layers, live/provider boundaries, acceptance |
| Runtime care | [Operations](operations.md) | Startup, observability, migrations, recovery, reset |
| Problem diagnosis | [Troubleshooting](troubleshooting.md) | Symptoms, likely causes, safe remediation |
| Terms | [Glossary](glossary.md) | RAG, SEC, retrieval, evaluation, and lineage vocabulary |
| Durable choices | [Architecture decisions](decisions/README.md) | Context, alternatives, decisions, consequences |

The detailed human-review and benchmark-execution procedure remains in
[Retrieval ground-truth review](../evaluation/REVIEW.md). Generated field-level API contracts live
in [`api/openapi.yaml`](../api/openapi.yaml) and [`api/sec-filing-rag.http`](../api/sec-filing-rag.http).

## Writing boundaries

- Architecture explains relationships; pillar guides explain feature behavior.
- Getting started owns initial setup and the complete path to first accepted use.
- API documentation explains HTTP contracts; orchestration documentation explains Kestra behavior.
- Configuration states valid inputs; local development explains how to use them locally.
- Testing defines verification; operations defines runtime care; troubleshooting starts from a
  symptom.
- Decision records explain why a durable choice was made. They are not user instructions or current
  API references.
