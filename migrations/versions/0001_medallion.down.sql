BEGIN;
DROP SCHEMA IF EXISTS gold CASCADE; DROP SCHEMA IF EXISTS silver CASCADE; DROP SCHEMA IF EXISTS bronze CASCADE;
DROP TABLE IF EXISTS public.corpus_activation, public.llm_usage, public.ingestion_stage, public.ingestion_run, public.company, public.configuration_version CASCADE;
DROP TYPE IF EXISTS public.usage_status, public.corpus_lifecycle, public.coverage_status, public.stage_status, public.run_status, public.resolution_status;
COMMIT;
