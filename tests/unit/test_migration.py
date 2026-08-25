from pathlib import Path


def test_devcontainer_runs_migrations_after_each_start() -> None:
    configuration = Path(".devcontainer/devcontainer.json").read_text(encoding="utf-8")
    script = Path(".devcontainer/post-start.sh").read_text(encoding="utf-8")
    assert '"postStartCommand": ".devcontainer/post-start.sh"' in configuration
    assert "pg_isready" in script
    assert script.count("uv run sec-rag-migrate") == 1
    assert "max_attempts=30" in script


def test_corpus_status_groups_correlated_company_key() -> None:
    migration = Path("migrations/versions/0001_schema.sql").read_text(encoding="utf-8")
    view = migration.split("CREATE VIEW gold.corpus_status AS", 1)[1]
    assert "ir.company_id = c.id" in view
    assert "GROUP BY c.id, c.ticker" in view


def test_clean_schema_has_historical_state_default_pointer_and_no_cross_database_fk() -> None:
    migration = Path("migrations/versions/0001_schema.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE public.filing_batch" in migration
    assert "CREATE TABLE public.filing_batch_item" in migration
    assert "CREATE TABLE bronze.filing_acquisition" in migration
    assert "preparation_request" not in migration
    assert "preparation_status" not in migration
    assert "confirmation_state" not in migration
    assert "requested_item" not in migration
    assert "preparation_request_id" not in migration
    assert not Path("migrations/versions/0002_filing_batches.sql").exists()
    assert "kestra_execution_id text" in migration
    assert "one_default_corpus_per_company" in migration
    assert "UNIQUE (filing_id, compatibility_key)" in migration
    assert "kestra_postgres" not in migration
    assert "FOREIGN DATA" not in migration

    initialization = Path(".devcontainer/postgres/init/00-extensions.sql").read_text(
        encoding="utf-8"
    )
    compose = Path(".devcontainer/docker-compose.yml").read_text(encoding="utf-8")
    assert "CREATE EXTENSION IF NOT EXISTS vector" in initialization
    assert "CREATE EXTENSION IF NOT EXISTS pg_textsearch" in initialization
    assert "shared_preload_libraries=pg_textsearch" in compose
