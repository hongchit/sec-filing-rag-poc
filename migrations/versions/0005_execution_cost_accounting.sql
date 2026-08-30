BEGIN;

ALTER TABLE public.filing_batch_item
  ADD COLUMN ingestion_run_id uuid UNIQUE REFERENCES public.ingestion_run(id);

ALTER TABLE public.retrieval_evaluation_run
  ADD COLUMN pricing_snapshot jsonb;

ALTER TABLE public.generation_evaluation_run
  ADD COLUMN pricing_snapshot jsonb;

ALTER TABLE public.ground_truth_generation_run
  ADD COLUMN pricing_snapshot jsonb;

COMMIT;
