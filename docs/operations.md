# Operations

## Setup, configuration, and ports

Open the repository in its Dev Container. The create hook installs locked Python dependencies, `httpgenerator` 1.1.0, frontend dependencies, and Codex. Copy `.env.example` to `.env`; do not commit it. Variables fall into SEC identity/rate and input bounds, OpenAI model/key, application/runtime/chunking, application PostgreSQL/pool, Kestra client/basic auth, and the base64 Kestra secret containing the same raw internal bearer token.

Local ports are FastAPI 8000, Vite 5173, application PostgreSQL 5432, Kestra UI/API 18082, and Kestra management 18083. The two PostgreSQL services share initialization credentials but separate volumes and responsibilities.

## Initialize and start

The post-start hook waits for PostgreSQL and runs `uv run sec-rag-migrate`. It is safe to run the migration command again. Start the API with `uv run sec-rag-api`, and optionally the shell with `npm --prefix frontend run dev`. Import/re-import `workflows/filing_batch.yaml` in Kestra; its namespace is `sec_filings.ingestion` and ID is `filing_batch`.

```bash
curl --fail-with-body -i http://127.0.0.1:8000/api/health
curl --fail-with-body -i http://127.0.0.1:8000/api/companies
curl --fail-with-body -i http://127.0.0.1:18082/api/v1/main/configs
```

Submit and poll using the examples in the README. Include `X-Request-ID: <safe-id>` when diagnosing a request; FastAPI returns the accepted/generated ID and emits structured logs with it. Batch responses contain the Kestra execution ID. Application logs explain API/policy failures; Kestra logs show task attempts; `filing_batch`, `filing_batch_item`, `ingestion_run`, and `ingestion_stage` show durable state.

## Failure and recovery

Kestra retries selection/acquisition/processing calls and the failure/finalization callbacks three times. A failed item is terminal and later items continue. `finally` always calls finalization, which converts stranded states to failed and calculates the aggregate. Safe retries reuse acquisitions by company/accession/checksum and corpora by filing/compatibility key. Resubmit a batch after correcting provider, credentials, or infrastructure; prior successful/default data remains intact. Do not manually edit states unless investigating with a disposable database.

Useful inspection:

```bash
psql "$DATABASE_URL" -c "select id,mode,fiscal_year,status,kestra_execution_id,safe_error from public.filing_batch order by created_at desc"
psql "$DATABASE_URL" -c "select batch_id,position,status,selected_accession,acquisition_id,corpus_version_id,safe_error from public.filing_batch_item order by batch_id,position"
psql "$DATABASE_URL" -c "select id,trigger,status,stage,section_count,chunk_count,safe_error from public.ingestion_run order by created_at desc"
psql "$DATABASE_URL" -c "select ticker,accession,item,coverage_status,chunk_count,search_document_count from gold.corpus_status order by ticker,item"
```

## Destructive fresh-start reset

The consolidated `0001_schema.sql` intentionally has no upgrade path from initialized old volumes. The following deletes both application data and Kestra history. Stop the Dev Container first, confirm the Compose project is this repository, and run from the repository root:

```bash
docker compose --env-file .env -f .devcontainer/docker-compose.yml down --volumes
```

Reopen/rebuild the Dev Container, run the migration, and re-import the flow. The removed named volumes are not recoverable unless separately backed up.

## Artifacts, verification, and acceptance

Regenerate/check OpenAPI and REST Client files with `sec-rag-export-openapi` and `sec-rag-generate-http`. Use the README's **Formatting and linting** section for the canonical fix and non-mutating verification commands, then run its full verification command set. Live acceptance requires working SEC/OpenAI/Kestra credentials: submit one latest batch and one exact-year batch, poll both terminal, confirm six coverage rows and matching present chunk/search counts, then confirm the exact-year corpus is listed as historical and did not change `active_corpus`. Live SEC tests are opt-in (`pytest -m live_edgar`).
