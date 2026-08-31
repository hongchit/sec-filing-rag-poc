# Local development

The repository is designed to run inside its Dev Container. [Getting started](getting-started.md)
owns cloning, initial configuration, workflow import, ingestion, evaluation, and first use. This
guide covers ports and recurring development work after that setup. The container pins Python and
Node dependencies, provides PostgreSQL and Kestra, shares package caches, and runs migration checks
after startup.

## Prerequisites

- Docker with Dev Container support
- Git
- SEC identity and OpenAI credentials
- Sufficient local storage for filing HTML, PostgreSQL, frontend dependencies, and model caches

Complete the prerequisites and `.env` procedure in [Getting started](getting-started.md).
Environment meanings and compatibility effects are documented in [Configuration](configuration.md).

## Local services and ports

| Service | Port | Purpose |
| --- | ---: | --- |
| FastAPI | 8000 | Public and internal application API |
| Vite | 5173 | React development server |
| Application PostgreSQL | 5432 | Corpus, research, evaluation, and workflow references |
| Kestra UI/API | 18082 | Flow import, execution, and inspection |
| Kestra management | 18083 | Kestra management endpoint |

Application and Kestra PostgreSQL data use different volumes. Do not connect application queries to
the Kestra database.

## Initialize and run

The post-start hook waits for application PostgreSQL and runs migrations. Repeating the migration
command is safe:

```bash
# Apply any pending application migrations.
uv run sec-rag-migrate

# Start the backend API.
uv run sec-rag-api
```

In a second terminal:

```bash
# Start the frontend development server with hot reload.
npm --prefix frontend run dev
```

Import or re-import `workflows/filing_batch.yaml` in Kestra. Its namespace is
`sec_filings.ingestion` and its flow ID is `filing_batch`.

Confirm local readiness:

```bash
# Confirm FastAPI and its database are ready.
curl --fail-with-body http://127.0.0.1:8000/api/health

# Confirm configured-company status is readable.
curl --fail-with-body http://127.0.0.1:8000/api/companies

# Confirm the local Kestra API is reachable.
curl --fail-with-body http://127.0.0.1:18082/api/v1/main/configs
```

## Daily development commands

Format and fix code:

```bash
# Apply automatic Python lint fixes, then normalize Python formatting.
uv run ruff check --fix .
uv run ruff format .

# Apply frontend lint fixes, then normalize frontend formatting.
npm --prefix frontend run lint:fix
npm --prefix frontend run format
```

Run focused tests while editing:

```bash
# Exercise retrieval behavior while editing retrieval code.
uv run pytest tests/unit/test_retrieval.py

# Exercise paragraph/highlight behavior while editing the reader backend.
uv run pytest tests/unit/test_corpus_reader.py

# Run all frontend unit and interaction tests.
npm --prefix frontend run test
```

Run the complete non-live verification set before handoff; [Testing](testing.md) owns that command
and explains which checks can call providers.

## Generated API artifacts

After changing routes or response schemas:

```bash
# Regenerate the field-level OpenAPI contract from FastAPI.
uv run sec-rag-export-openapi

# Regenerate the REST Client request collection from OpenAPI.
uv run sec-rag-generate-http
```

Review both generated diffs. Do not edit `api/openapi.yaml` or `api/sec-filing-rag.http` by hand.

## Database changes

Add the next numbered file under `migrations/versions`; never edit a migration that may have been
applied. Run `uv run sec-rag-migrate` and the migration tests. The safe destructive local reset is an
operational procedure and remains in [Operations](operations.md).

## Working with external services

SEC and OpenAI calls can incur rate, availability, and cost constraints. Unit and API tests use
fakes or stored fixtures. Run live tests or corpus/evaluation generation only when credentials,
account limits, expected workload, and output destinations have been reviewed.
