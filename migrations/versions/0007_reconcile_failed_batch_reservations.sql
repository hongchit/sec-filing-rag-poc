BEGIN;

-- Release reservations for historical batches that failed before Kestra or model work began.
UPDATE public.cost_action AS action
   SET status = 'reconciled',
       charged_usd = 0,
       reconciled_at = now()
  FROM public.filing_batch AS batch
 WHERE action.filing_batch_id = batch.id
   AND action.status = 'reserved'
   AND batch.status = 'failed'
   AND batch.kestra_execution_id IS NULL
   AND batch.safe_error LIKE 'Client error ''401 Unauthorized''%'
   AND NOT EXISTS (
         SELECT 1
           FROM public.filing_batch_item AS item
           JOIN public.llm_usage AS usage
             ON usage.ingestion_run_id = item.ingestion_run_id
          WHERE item.batch_id = batch.id
       );

COMMIT;
