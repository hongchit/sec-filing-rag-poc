# SEC Filing RAG proof of concept

This repository implements a local, API-initiated pipeline for original SEC 10-K filings. It supports persisted multi-company batches, latest and exact report-year selection, historical corpora, six-Item extraction, deterministic chunks, OpenAI embeddings, keyword/vector/hybrid retrieval, and reviewed retrieval evaluation. FastAPI owns business state and policy; Kestra runs one sequential `filing_batch` flow. The React frontend is currently only a health shell, not an ingestion or search UI.

## Quick start

Copy `.env.example` to `.env` and replace every placeholder. A truthful SEC identity, OpenAI key, application database credentials, Kestra credentials, and a shared ingestion token are required. Rebuild/open the Dev Container, then:

```bash
uv run sec-rag-migrate
uv run sec-rag-api
npm --prefix frontend run dev
```

Import `workflows/filing_batch.yaml` through the Kestra UI at <http://127.0.0.1:18082>. The API is on port 8000, frontend 5173, application PostgreSQL 5432, and Kestra 18082 (management 18083).

The schema is intentionally fresh-start-only. If an existing application volume has either old migration, use the destructive reset in [operations](docs/operations.md) before migrating; there is no compatibility upgrade.

## Submit and poll

```bash
# Latest original 10-K for all enabled companies
curl --fail-with-body -i -X POST http://127.0.0.1:8000/api/filing-batches \
  -H 'Content-Type: application/json' -d '{}'

# Exact SEC report-date year for an ordered subset
curl --fail-with-body -i -X POST http://127.0.0.1:8000/api/filing-batches \
  -H 'Content-Type: application/json' \
  -d '{"tickers":["AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","JPM","XOM","JNJ"],"fiscal_year":2024}'

# One-company convenience route
curl --fail-with-body -i -X POST http://127.0.0.1:8000/api/companies/AAPL/filing-preparations \
  -H 'Content-Type: application/json' -d '{"fiscal_year":2024}'

curl --fail-with-body -i http://127.0.0.1:8000/api/filing-batches/$BATCH_ID
curl --fail-with-body -i http://127.0.0.1:8000/api/companies/AAPL/status
```

A missing exact year is skipped, never replaced by a neighbor. Exact-year corpora never become default. Latest mode skips an already-active compatible corpus and promotes a compatible ready historical corpus without re-embedding.

## Formatting and linting

Format and automatically fix Python and frontend code from the repository root:

```bash
uv run ruff check --fix .
uv run ruff format .
npm --prefix frontend run lint:fix
npm --prefix frontend run format
```

Verify formatting, linting, and types without changing files:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
npm --prefix frontend run check
```

## Generated artifacts and verification

```bash
uv run sec-rag-export-openapi
uv run sec-rag-generate-http
uv run ruff format --check .
uv run ruff check .
uv run mypy
EDGAR_LOCAL_DATA_DIR=/tmp/edgar-cache uv run pytest
npm --prefix frontend run check
bash -n .devcontainer/post-create.sh .devcontainer/post-start.sh
docker compose --env-file .env -f .devcontainer/docker-compose.yml config --quiet
uv run sec-rag-export-openapi --check
uv run sec-rag-generate-http --check
```

Generated contracts live in `api/openapi.yaml` and `api/sec-filing-rag.http`. Retrieval generation/evaluation outputs are described in [evaluation/REVIEW.md](evaluation/REVIEW.md).

## Documentation map

- [Architecture](docs/architecture.md): components, boundaries, data flow, invariants, and package map.
- [Operations](docs/operations.md): setup, reset, startup, observability, recovery, and acceptance.
- [API and orchestration](docs/api-orchestration-design.md): endpoint contracts, sequences, states, and Kestra graph.
- [Corpus pipeline](docs/corpus-pipeline.md): acquisition-to-activation processing and lineage.
- [Database schema](docs/database-schema.md): durable tables, constraints, and ownership.
- [Glossary](docs/glossary.md): project terminology.
- [Corpus learnings](docs/corpus-learnings.md): filing edge cases and regression rationale.
- [Ground-truth review](evaluation/REVIEW.md): corpus preparation through retrieval evaluation.
