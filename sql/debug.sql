SELECT *
FROM bronze.filing_acquisition
LIMIT 10;

select id,mode,fiscal_year,status,kestra_execution_id,safe_error from public.filing_batch order by created_at desc

select batch_id,position,status,selected_accession,acquisition_id,corpus_version_id,safe_error from public.filing_batch_item order by batch_id,position

select id,trigger,status,stage,section_count,chunk_count,safe_error from public.ingestion_run order by created_at desc

select ticker,accession,item,coverage_status,chunk_count,search_document_count from gold.corpus_status order by ticker,item

