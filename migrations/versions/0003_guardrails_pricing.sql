BEGIN;

CREATE TYPE public.research_disposition AS ENUM ('answered', 'investment_advice', 'out_of_scope');

ALTER TABLE public.research_request
  ADD COLUMN pricing_snapshot jsonb;

ALTER TABLE public.research_result
  ADD COLUMN disposition public.research_disposition NOT NULL DEFAULT 'answered',
  ADD COLUMN rejection_message text;

UPDATE public.research_result
SET disposition = CASE WHEN policy_refusal THEN 'investment_advice'::public.research_disposition
                       ELSE 'answered'::public.research_disposition END,
    answer = CASE WHEN policy_refusal THEN '[]'::jsonb ELSE answer END,
    limitations = CASE WHEN policy_refusal THEN '[]'::jsonb ELSE limitations END,
    insufficient_evidence = CASE WHEN policy_refusal THEN false ELSE insufficient_evidence END,
    rejection_message = CASE WHEN policy_refusal THEN
      'This tool cannot answer requests for investment recommendations, trades, price targets, or price and return predictions. Ask a question about disclosures in the selected company''s Form 10-K.'
      ELSE NULL END;

ALTER TABLE public.research_result
  ADD CONSTRAINT research_result_disposition_consistent CHECK (
    (disposition = 'answered' AND policy_refusal = false AND rejection_message IS NULL)
    OR
    (disposition = 'investment_advice' AND policy_refusal = true AND rejection_message IS NOT NULL
      AND answer = '[]'::jsonb AND limitations = '[]'::jsonb AND insufficient_evidence = false)
    OR
    (disposition = 'out_of_scope' AND policy_refusal = false AND rejection_message IS NOT NULL
      AND answer = '[]'::jsonb AND limitations = '[]'::jsonb AND insufficient_evidence = false)
  );

COMMIT;
