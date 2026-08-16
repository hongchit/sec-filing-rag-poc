BEGIN;
DROP SCHEMA IF EXISTS gold CASCADE;
DROP SCHEMA IF EXISTS silver CASCADE;
DROP SCHEMA IF EXISTS bronze CASCADE;
DROP TABLE IF EXISTS public.corpus_activation, public.llm_usage, public.ingestion_stage,
  public.ingestion_run, public.preparation_request, public.company,
  public.configuration_version, public.schema_migration CASCADE;
DROP TYPE IF EXISTS public.confirmation_state, public.preparation_status, public.usage_status,
  public.corpus_lifecycle, public.coverage_status, public.stage_status, public.run_status,
  public.resolution_status;
COMMIT;
