#!/usr/bin/env bash
set -euo pipefail

cd /workspaces/sec-filing-rag-poc

readonly max_attempts=30
for ((attempt = 1; attempt <= max_attempts; attempt++)); do
  if pg_isready --host=db --port=5432 --dbname="${POSTGRES_DB:?POSTGRES_DB is required}" \
    --username="${POSTGRES_USER:?POSTGRES_USER is required}" >/dev/null 2>&1; then
    uv run sec-rag-migrate
    exit 0
  fi
  sleep 2
done

echo "Application PostgreSQL did not become ready at db:5432 within 60 seconds." >&2
echo "Check the db service and DATABASE_URL, then restart the Dev Container." >&2
exit 1
