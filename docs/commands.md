# Command reference

This page indexes the commands defined by this repository. Run commands from the repository root
inside the Dev Container unless a section says otherwise. It summarizes purpose and syntax; the
linked guide remains authoritative for prerequisites, sequencing, review decisions, cost, and
failure handling.

## Discover command options

Python application commands are registered under `[project.scripts]` in `pyproject.toml` and should
be invoked through `uv run`. Commands backed by `argparse` expose detailed option help:

```bash
# Show the current options for one argument-based project command.
uv run sec-rag-evaluate-retrieval --help
```

Frontend commands are registered under `scripts` in `frontend/package.json` and are invoked with
`npm --prefix frontend run <script>`.

## Runtime and database

| Command | Purpose | Details |
| --- | --- | --- |
| `uv run sec-rag-migrate` | Apply missing application migrations and reject changed applied migrations | [Local development](local-development.md#database-changes), [Operations](operations.md#migrations) |
| `uv run sec-rag-api` | Start FastAPI using `APP_HOST` and `APP_PORT` | [Getting started](getting-started.md#4-start-the-application-and-import-the-workflow), [Operations](operations.md#startup-and-readiness) |

The Dev Container post-start hook runs the migrator automatically after PostgreSQL becomes ready;
running it again is safe.

## Retrieval inspection and evaluation

| Command | Purpose | Important inputs | Details |
| --- | --- | --- | --- |
| `uv run sec-rag-search QUESTION --ticker TICKER --corpus-version-id UUID` | Inspect corpus-scoped retrieval | Optional `--strategy`, `--items`, `--candidate-count`, `--top-k`, `--alpha`, and `--rrf-k` | [Retrieval evaluation guide](retrieval-evaluation-workflow.md) |
| `uv run sec-rag-evaluate-retrieval --validate-only` | Validate the reviewed dataset, manifest, embedding contract, and database lineage without benchmarking | Optional `--dataset`, `--manifest`, and `--output-dir` | [Ground-truth review runbook](../evaluation/REVIEW.md#7-validate-and-run-retrieval-evaluation) |
| `uv run sec-rag-evaluate-retrieval` | Run the complete configured retrieval grid and write result artifacts | Same path options as validation | [Ground-truth review runbook](../evaluation/REVIEW.md#7-validate-and-run-retrieval-evaluation) |

Retrieval benchmarking calls the embedding provider and must use a finalized, locally
lineage-compatible dataset.

## Ground-truth preparation

All ground-truth subcommands accept optional `--review-bundle`, `--config`, and `--prompt` paths.

| Command | Purpose | Additional options | Details |
| --- | --- | --- | --- |
| `uv run sec-rag-generate-ground-truth generate` | Snapshot compatible ready corpora and generate model-assisted review candidates | `--diagnostic`, `--run-id`, `--resume` | [Generate the review bundle](../evaluation/REVIEW.md#4-generate-the-review-bundle) |
| `uv run sec-rag-generate-ground-truth validate-review --allow-pending` | Validate bundle structure while human decisions remain incomplete | `--allow-pending` | [Review and edit](../evaluation/REVIEW.md#5-review-and-edit-the-generated-ground-truth) |
| `uv run sec-rag-generate-ground-truth validate-review` | Require complete, valid human decisions | None beyond common paths | [Review and edit](../evaluation/REVIEW.md#5-review-and-edit-the-generated-ground-truth) |
| `uv run sec-rag-generate-ground-truth finalize` | Create checksum-bound retrieval JSONL and manifest artifacts | `--dataset`, `--manifest` | [Finalize the dataset](../evaluation/REVIEW.md#6-finalize-the-reviewed-dataset) |

`generate` is network- and cost-bearing. Validation and finalization do not establish that model
proposals are correct; human review is the trust boundary.

## Full-RAG evaluation

| Command | Purpose | Important inputs | Details |
| --- | --- | --- | --- |
| `uv run sec-rag-run-generation-evaluation --output-json PATH --output-markdown PATH --validate-only` | Preflight dataset, lineage, models, prompts, pricing, paths, and expected call counts without provider calls or artifact writes | Optional repeated `--prompt-id`, `--judge-prompt`, `--workers`, `--dataset`, and `--manifest` | [Full-RAG evaluation guide](rag-evaluation-workflow.md#controlled-batches) |
| `uv run sec-rag-run-generation-evaluation --output-json PATH --output-markdown PATH` | Run live retrieval, answer generation, citation audit, and judging with stage-by-stage progress on `stderr` | Same optional inputs plus `--no-progress`; output paths must not exist | [Full-RAG evaluation guide](rag-evaluation-workflow.md) |
| `uv run sec-rag-evaluate-generation ARTIFACT` | Validate an existing generation-evaluation artifact against reviewed inputs | Optional `--dataset`, `--manifest`, and new `--markdown` output path | [Full-RAG evaluation guide](rag-evaluation-workflow.md#controlled-batches) |

The live runner is network- and cost-bearing and records database audit/usage rows. The standalone
validator makes no provider calls and performs no database writes. Neither command promotes a
prompt automatically. Live progress is enabled by default; use `--no-progress` when an automation
consumer needs only the final JSON record on `stdout`.

## Generated API contracts

| Command | Purpose | Details |
| --- | --- | --- |
| `uv run sec-rag-export-openapi` | Regenerate `api/openapi.yaml` from FastAPI | [API reference](api.md#generated-contracts) |
| `uv run sec-rag-export-openapi --check` | Fail if the checked-in OpenAPI artifact is stale | [Testing](testing.md#normal-verification) |
| `uv run sec-rag-generate-http` | Regenerate `api/sec-filing-rag.http` from OpenAPI | [API reference](api.md#generated-contracts) |
| `uv run sec-rag-generate-http --check` | Fail if the checked-in REST Client artifact is stale | [Testing](testing.md#normal-verification) |

Do not edit either generated contract manually. The REST Client collection remains the executable
HTTP reference; Markdown documentation should link to it rather than duplicate request blocks.

## Frontend commands

| Command | Purpose | Details |
| --- | --- | --- |
| `npm --prefix frontend run dev` | Start Vite with hot reload on port 5173 | [Getting started](getting-started.md#4-start-the-application-and-import-the-workflow) |
| `npm --prefix frontend run build` | Type-check and create a production build | [Testing](testing.md) |
| `npm --prefix frontend run test` | Run Vitest unit and interaction tests | [Testing](testing.md) |
| `npm --prefix frontend run lint` | Check frontend ESLint rules | [Local development](local-development.md#daily-development-commands) |
| `npm --prefix frontend run lint:fix` | Apply safe ESLint fixes | [Local development](local-development.md#daily-development-commands) |
| `npm --prefix frontend run format` | Format tracked frontend source/configuration files | [Local development](local-development.md#daily-development-commands) |
| `npm --prefix frontend run format:check` | Check frontend formatting without rewriting files | [Testing](testing.md#normal-verification) |
| `npm --prefix frontend run check` | Run formatting, lint, tests, TypeScript, and production build | [Testing](testing.md#normal-verification) |

## Python development and verification

These are tool commands rather than application entry points:

| Command | Purpose | Details |
| --- | --- | --- |
| `uv sync --frozen --all-packages` | Install the exact locked Python environment | Automated by the Dev Container; [Getting started](getting-started.md) |
| `uv run ruff format --check .` | Check Python formatting | [Testing](testing.md#normal-verification) |
| `uv run ruff format .` | Apply Python formatting | [Local development](local-development.md#daily-development-commands) |
| `uv run ruff check .` | Run Python lint rules | [Testing](testing.md#normal-verification) |
| `uv run ruff check --fix .` | Apply safe Python lint fixes | [Local development](local-development.md#daily-development-commands) |
| `uv run mypy` | Run strict Python type checking | [Testing](testing.md#normal-verification) |
| `EDGAR_LOCAL_DATA_DIR=/tmp/edgar-cache uv run pytest` | Run the provider-free backend suite with a writable disposable SEC cache | [Testing](testing.md#normal-verification) |
| `EDGAR_LOCAL_DATA_DIR=/tmp/edgar-cache uv run pytest -m live_edgar` | Run opt-in live SEC acceptance tests | [Testing](testing.md#live-and-cost-bearing-checks) |

## Container and infrastructure checks

| Command | Purpose | Details |
| --- | --- | --- |
| `bash -n .devcontainer/post-create.sh .devcontainer/post-start.sh` | Parse Dev Container hooks without executing them | [Testing](testing.md#normal-verification) |
| `docker compose --env-file .env -f .devcontainer/docker-compose.yml config --quiet` | Validate the resolved local Compose configuration | [Testing](testing.md#normal-verification) |

Destructive database-reset commands are intentionally not summarized here. Resolve and verify the
exact target by following [Reset only the application database](operations.md#reset-only-the-application-database-destructive).
