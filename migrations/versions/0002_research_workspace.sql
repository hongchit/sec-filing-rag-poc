BEGIN;

ALTER TABLE public.research_request
  ADD COLUMN idempotency_key uuid UNIQUE,
  ADD COLUMN retrieval_configuration_sha256 char(64),
  ADD COLUMN generation_configuration_sha256 char(64),
  ADD COLUMN prompt_sha256 char(64),
  ADD COLUMN accession text;

ALTER TABLE public.research_result
  ADD COLUMN policy_refusal boolean NOT NULL DEFAULT false;

CREATE INDEX research_request_created
  ON public.research_request(created_at DESC, id DESC);

CREATE TYPE public.feedback_rating AS ENUM ('up', 'down');
CREATE TABLE public.feedback (
  id uuid PRIMARY KEY,
  rating public.feedback_rating NOT NULL,
  research_id uuid REFERENCES public.research_request(id) ON DELETE CASCADE,
  comment text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (num_nonnulls(research_id) = 1),
  CHECK (comment IS NULL OR (length(btrim(comment)) BETWEEN 1 AND 1000 AND comment = btrim(comment))),
  UNIQUE (research_id)
);

COMMIT;
