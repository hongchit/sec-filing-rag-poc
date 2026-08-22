BEGIN;

CREATE TYPE public.filing_batch_mode AS ENUM ('latest','exact_year');
CREATE TYPE public.filing_batch_status AS ENUM ('submitted','running','succeeded','partial_failure','failed');
CREATE TYPE public.filing_batch_item_status AS ENUM
  ('pending','selecting','acquiring','processing','succeeded','skipped','failed');

CREATE TABLE public.filing_batch (
  id uuid PRIMARY KEY,
  mode public.filing_batch_mode NOT NULL,
  fiscal_year integer CHECK (fiscal_year IS NULL OR fiscal_year BETWEEN 1900 AND 9999),
  status public.filing_batch_status NOT NULL DEFAULT 'submitted',
  request_id text,
  kestra_execution_id text,
  safe_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  CHECK ((mode='latest' AND fiscal_year IS NULL) OR (mode='exact_year' AND fiscal_year IS NOT NULL))
);

CREATE TABLE public.filing_batch_item (
  id uuid PRIMARY KEY,
  batch_id uuid NOT NULL REFERENCES public.filing_batch(id),
  company_id uuid NOT NULL REFERENCES public.company(id),
  position integer NOT NULL CHECK (position >= 0),
  status public.filing_batch_item_status NOT NULL DEFAULT 'pending',
  selected_accession text CHECK (selected_accession IS NULL OR selected_accession ~ '^[0-9]{10}-[0-9]{2}-[0-9]{6}$'),
  acquisition_id uuid,
  corpus_version_id uuid REFERENCES silver.corpus_version(id),
  safe_error text,
  started_at timestamptz,
  finished_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (batch_id, position),
  UNIQUE (batch_id, company_id)
);

CREATE TABLE bronze.filing_acquisition (
  id uuid PRIMARY KEY,
  company_id uuid NOT NULL REFERENCES public.company(id),
  accession text NOT NULL CHECK (accession ~ '^[0-9]{10}-[0-9]{2}-[0-9]{6}$'),
  payload jsonb NOT NULL,
  content bytea NOT NULL,
  media_type text NOT NULL CHECK (media_type='text/html'),
  content_sha256 char(64) NOT NULL,
  content_length bigint NOT NULL CHECK (content_length=octet_length(content)),
  acquired_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, accession, content_sha256)
);

ALTER TABLE public.filing_batch_item
  ADD CONSTRAINT filing_batch_item_acquisition_fk
  FOREIGN KEY (acquisition_id) REFERENCES bronze.filing_acquisition(id);

CREATE INDEX filing_batch_item_order ON public.filing_batch_item(batch_id, position);

COMMIT;
