BEGIN;

ALTER TABLE public.filing_batch
  ADD COLUMN launcher_execution_id text UNIQUE;

COMMIT;
