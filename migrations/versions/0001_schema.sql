BEGIN;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_textsearch;
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TYPE public.resolution_status AS ENUM ('pending','resolved','failed');
CREATE TYPE public.run_status AS ENUM ('pending','running','succeeded','failed','skipped');
CREATE TYPE public.stage_status AS ENUM ('pending','running','succeeded','failed','skipped');
CREATE TYPE public.coverage_status AS ENUM ('present','legitimately_absent','failed','not_assessed');
CREATE TYPE public.corpus_lifecycle AS ENUM ('building','ready','failed','retired');
CREATE TYPE public.usage_status AS ENUM ('reported','unavailable','failed');
CREATE TYPE public.filing_batch_mode AS ENUM ('latest','exact_year');
CREATE TYPE public.filing_batch_status AS ENUM ('submitted','running','succeeded','partial_failure','failed');
CREATE TYPE public.filing_batch_item_status AS ENUM ('pending','selecting','acquiring','processing','succeeded','skipped','failed');

CREATE TABLE public.configuration_version (
  id uuid PRIMARY KEY, kind text NOT NULL, path text NOT NULL, normalized_json jsonb NOT NULL,
  sha256 char(64) NOT NULL UNIQUE, loaded_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.company (
  id uuid PRIMARY KEY, ticker text NOT NULL UNIQUE CHECK (ticker = upper(ticker) AND ticker ~ '^[A-Z][A-Z0-9.-]{0,9}$'),
  enabled boolean NOT NULL, cik text CHECK (cik IS NULL OR cik ~ '^[0-9]{10}$'), name text,
  resolution_status public.resolution_status NOT NULL DEFAULT 'pending', safe_error text,
  configuration_version_id uuid NOT NULL REFERENCES public.configuration_version(id), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.filing_batch (
  id uuid PRIMARY KEY, mode public.filing_batch_mode NOT NULL,
  fiscal_year integer CHECK (fiscal_year IS NULL OR fiscal_year BETWEEN 1900 AND 9999),
  status public.filing_batch_status NOT NULL DEFAULT 'submitted', request_id text,
  kestra_execution_id text, safe_error text, created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
  CHECK ((mode='latest' AND fiscal_year IS NULL) OR (mode='exact_year' AND fiscal_year IS NOT NULL))
);
CREATE TABLE bronze.filing_acquisition (
  id uuid PRIMARY KEY, company_id uuid NOT NULL REFERENCES public.company(id),
  accession text NOT NULL CHECK (accession ~ '^[0-9]{10}-[0-9]{2}-[0-9]{6}$'),
  payload jsonb NOT NULL, content bytea NOT NULL, media_type text NOT NULL CHECK (media_type='text/html'),
  content_sha256 char(64) NOT NULL, content_length bigint NOT NULL CHECK (content_length=octet_length(content)),
  acquired_at timestamptz NOT NULL DEFAULT now(), UNIQUE (company_id, accession, content_sha256)
);
CREATE TABLE public.ingestion_run (
  id uuid PRIMARY KEY, company_id uuid NOT NULL REFERENCES public.company(id),
  trigger text NOT NULL CHECK (trigger IN ('latest','exact_year','test')), compatibility_key char(64) NOT NULL,
  kestra_execution_id text,
  status public.run_status NOT NULL DEFAULT 'pending', stage text NOT NULL DEFAULT 'created',
  section_count integer NOT NULL DEFAULT 0 CHECK (section_count >= 0), chunk_count integer NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
  started_at timestamptz, finished_at timestamptz, safe_error text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.ingestion_stage (
  id bigserial PRIMARY KEY, ingestion_run_id uuid NOT NULL REFERENCES public.ingestion_run(id), stage text NOT NULL,
  status public.stage_status NOT NULL, attempt integer NOT NULL DEFAULT 1 CHECK (attempt > 0),
  input_count integer CHECK (input_count >= 0), output_count integer CHECK (output_count >= 0),
  started_at timestamptz, finished_at timestamptz, safe_error text, UNIQUE (ingestion_run_id, stage, attempt)
);
CREATE TABLE public.llm_usage (
  id bigserial PRIMARY KEY, ingestion_run_id uuid NOT NULL REFERENCES public.ingestion_run(id), operation text NOT NULL,
  model text NOT NULL, input_tokens integer CHECK (input_tokens IS NULL OR input_tokens >= 0),
  output_tokens integer CHECK (output_tokens IS NULL OR output_tokens >= 0), total_tokens integer CHECK (total_tokens IS NULL OR total_tokens >= 0),
  latency_ms integer CHECK (latency_ms IS NULL OR latency_ms >= 0), usage_status public.usage_status NOT NULL,
  normalized_status text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE bronze.edgar_company_snapshot (
  id uuid PRIMARY KEY, requested_ticker text NOT NULL, cik text NOT NULL CHECK (cik ~ '^[0-9]{10}$'), legal_name text NOT NULL,
  tickers text[] NOT NULL, exchanges text[] NOT NULL, sic text, industry text, fiscal_year_end text, filer_type text, is_company boolean,
  edgartools_version text NOT NULL, edgar_identity_hash char(64) NOT NULL, acquired_at timestamptz NOT NULL DEFAULT now(),
  canonical_metadata_sha256 char(64) NOT NULL UNIQUE
);
CREATE TABLE bronze.edgar_filing_snapshot (
  id uuid PRIMARY KEY, company_snapshot_id uuid NOT NULL REFERENCES bronze.edgar_company_snapshot(id),
  accession text NOT NULL CHECK (accession ~ '^[0-9]{10}-[0-9]{2}-[0-9]{6}$'), form text NOT NULL CHECK (form = '10-K'),
  filing_date date NOT NULL, report_date date NOT NULL, acceptance_datetime timestamptz, act text, file_number text,
  submission_size bigint CHECK (submission_size IS NULL OR submission_size >= 0), is_xbrl boolean, is_inline_xbrl boolean,
  primary_document text NOT NULL, primary_document_description text, homepage_url text NOT NULL, filing_url text NOT NULL, text_url text NOT NULL,
  edgartools_version text NOT NULL, acquired_at timestamptz NOT NULL DEFAULT now(), canonical_metadata_sha256 char(64) NOT NULL UNIQUE
);
CREATE TABLE bronze.edgar_filing_document (
  id uuid PRIMARY KEY, filing_snapshot_id uuid NOT NULL REFERENCES bronze.edgar_filing_snapshot(id), document_name text NOT NULL,
  document_type text NOT NULL CHECK (document_type = '10-K'), sequence_number text, description text, source_url text NOT NULL,
  content bytea NOT NULL, media_type text NOT NULL DEFAULT 'text/html' CHECK (media_type = 'text/html'),
  content_encoding text NOT NULL DEFAULT 'utf-8' CHECK (content_encoding = 'utf-8'),
  content_length bigint NOT NULL CHECK (content_length = octet_length(content)), content_sha256 char(64) NOT NULL UNIQUE,
  edgartools_version text NOT NULL, acquired_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE silver.filing (
  id uuid PRIMARY KEY, company_id uuid NOT NULL REFERENCES public.company(id),
  edgar_company_snapshot_id uuid NOT NULL REFERENCES bronze.edgar_company_snapshot(id),
  edgar_filing_snapshot_id uuid NOT NULL REFERENCES bronze.edgar_filing_snapshot(id),
  edgar_filing_document_id uuid NOT NULL REFERENCES bronze.edgar_filing_document(id),
  cik text NOT NULL, accession text NOT NULL, form text NOT NULL CHECK (form = '10-K'), primary_document text NOT NULL,
  filing_date date NOT NULL, report_date date NOT NULL, source_url text NOT NULL, UNIQUE (cik, accession)
);
CREATE TABLE silver.corpus_version (
  id uuid PRIMARY KEY, filing_id uuid NOT NULL REFERENCES silver.filing(id), ingestion_run_id uuid NOT NULL REFERENCES public.ingestion_run(id),
  compatibility_key char(64) NOT NULL, parser_version text NOT NULL, chunking_version text NOT NULL,
  embedding_model text NOT NULL, embedding_dimensions integer NOT NULL CHECK (embedding_dimensions > 0), index_version text NOT NULL,
  source_document_sha256 char(64) NOT NULL, edgartools_version text NOT NULL,
  status public.corpus_lifecycle NOT NULL DEFAULT 'building', created_at timestamptz NOT NULL DEFAULT now(), ready_at timestamptz,
  UNIQUE (filing_id, compatibility_key)
);
CREATE TABLE public.filing_batch_item (
  id uuid PRIMARY KEY, batch_id uuid NOT NULL REFERENCES public.filing_batch(id),
  company_id uuid NOT NULL REFERENCES public.company(id), position integer NOT NULL CHECK (position >= 0),
  status public.filing_batch_item_status NOT NULL DEFAULT 'pending',
  selected_accession text CHECK (selected_accession IS NULL OR selected_accession ~ '^[0-9]{10}-[0-9]{2}-[0-9]{6}$'),
  acquisition_id uuid REFERENCES bronze.filing_acquisition(id), corpus_version_id uuid REFERENCES silver.corpus_version(id),
  safe_error text, started_at timestamptz, finished_at timestamptz, updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (batch_id, position), UNIQUE (batch_id, company_id)
);
CREATE INDEX filing_batch_item_order ON public.filing_batch_item(batch_id, position);
CREATE TABLE silver.section (
  id uuid PRIMARY KEY, corpus_version_id uuid NOT NULL REFERENCES silver.corpus_version(id), filing_id uuid NOT NULL REFERENCES silver.filing(id),
  item text NOT NULL, coverage_status public.coverage_status NOT NULL, text_content text, source_start integer, source_end integer,
  source_anchor text, sha256 char(64), parser_version text NOT NULL, safe_error text,
  CHECK ((coverage_status = 'present' AND text_content IS NOT NULL AND sha256 IS NOT NULL) OR coverage_status <> 'present'),
  UNIQUE (corpus_version_id, item)
);
CREATE TABLE silver.chunk (
  id char(64) PRIMARY KEY, section_id uuid NOT NULL REFERENCES silver.section(id), corpus_version_id uuid NOT NULL REFERENCES silver.corpus_version(id),
  ordinal integer NOT NULL CHECK (ordinal >= 0), text_content text NOT NULL, source_start integer NOT NULL, source_end integer NOT NULL,
  citation_handle text NOT NULL, chunking_version text NOT NULL, sha256 char(64) NOT NULL,
  UNIQUE (section_id, ordinal), UNIQUE (corpus_version_id, citation_handle)
);
CREATE TABLE gold.search_document (
  chunk_id char(64) PRIMARY KEY REFERENCES silver.chunk(id), corpus_version_id uuid NOT NULL REFERENCES silver.corpus_version(id),
  company_id uuid NOT NULL REFERENCES public.company(id), filing_id uuid NOT NULL REFERENCES silver.filing(id),
  item text NOT NULL, text_content text NOT NULL, citation_handle text NOT NULL, provenance jsonb NOT NULL,
  embedding vector NOT NULL, embedding_model text NOT NULL, embedding_dimensions integer NOT NULL CHECK (embedding_dimensions > 0),
  lexical_document text, created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (vector_dims(embedding) = embedding_dimensions)
);
CREATE TABLE public.corpus_activation (
  id bigserial PRIMARY KEY, company_id uuid NOT NULL REFERENCES public.company(id), corpus_version_id uuid NOT NULL REFERENCES silver.corpus_version(id),
  ingestion_run_id uuid NOT NULL REFERENCES public.ingestion_run(id), is_default boolean NOT NULL DEFAULT true,
  activated_at timestamptz NOT NULL DEFAULT now(), deactivated_at timestamptz,
  CHECK ((is_default AND deactivated_at IS NULL) OR (NOT is_default AND deactivated_at IS NOT NULL))
);
CREATE UNIQUE INDEX one_default_corpus_per_company ON public.corpus_activation(company_id) WHERE is_default;

CREATE FUNCTION bronze.reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'bronze tables are insert-only'; END $$;
CREATE TRIGGER edgar_company_snapshot_immutable BEFORE UPDATE OR DELETE ON bronze.edgar_company_snapshot FOR EACH ROW EXECUTE FUNCTION bronze.reject_mutation();
CREATE TRIGGER edgar_filing_snapshot_immutable BEFORE UPDATE OR DELETE ON bronze.edgar_filing_snapshot FOR EACH ROW EXECUTE FUNCTION bronze.reject_mutation();
CREATE TRIGGER edgar_filing_document_immutable BEFORE UPDATE OR DELETE ON bronze.edgar_filing_document FOR EACH ROW EXECUTE FUNCTION bronze.reject_mutation();
CREATE VIEW gold.corpus_status AS
SELECT c.ticker, cv.id AS corpus_version_id, f.accession, f.filing_date, s.item, s.coverage_status,
       count(DISTINCT ch.id)::integer AS chunk_count, count(DISTINCT gd.chunk_id)::integer AS search_document_count,
       COALESCE((SELECT max(lu.usage_status::text) FROM public.llm_usage lu WHERE lu.ingestion_run_id = cv.ingestion_run_id), 'unavailable') AS embedding_usage_status,
       cv.embedding_model, cv.embedding_dimensions, ca.activated_at,
       (SELECT max(ir.finished_at) FROM public.ingestion_run ir WHERE ir.company_id = c.id AND ir.status = 'succeeded') AS latest_successful_ingestion
FROM public.corpus_activation ca JOIN public.company c ON c.id = ca.company_id
JOIN silver.corpus_version cv ON cv.id = ca.corpus_version_id JOIN silver.filing f ON f.id = cv.filing_id
JOIN silver.section s ON s.corpus_version_id = cv.id LEFT JOIN silver.chunk ch ON ch.section_id = s.id
LEFT JOIN gold.search_document gd ON gd.chunk_id = ch.id WHERE ca.is_default
GROUP BY c.id, c.ticker, cv.id, f.accession, f.filing_date, s.item, s.coverage_status, ca.activated_at;

CREATE INDEX search_document_lexical_bm25 ON gold.search_document USING bm25 (lexical_document) WITH (text_config='english');
CREATE INDEX search_document_company_corpus_filing ON gold.search_document (company_id, corpus_version_id, filing_id);
CREATE INDEX search_document_company_corpus_filing_item ON gold.search_document (company_id, corpus_version_id, filing_id, item);
CREATE TYPE public.evaluation_status AS ENUM ('running','succeeded','failed');
CREATE TABLE public.retrieval_evaluation_run (
  id uuid PRIMARY KEY, dataset_sha256 char(64) NOT NULL, configuration_sha256 char(64) NOT NULL,
  status public.evaluation_status NOT NULL DEFAULT 'running', selected_configuration jsonb, safe_error text,
  started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz
);
ALTER TABLE public.llm_usage ADD COLUMN evaluation_run_id uuid REFERENCES public.retrieval_evaluation_run(id);
ALTER TABLE public.llm_usage ALTER COLUMN ingestion_run_id DROP NOT NULL;
ALTER TABLE public.llm_usage ADD CONSTRAINT llm_usage_single_owner CHECK (
  (ingestion_run_id IS NOT NULL)::integer + (evaluation_run_id IS NOT NULL)::integer <= 1
);
CREATE TYPE public.ground_truth_generation_status AS ENUM ('running','succeeded','failed');
CREATE TABLE public.ground_truth_generation_run (
 id uuid PRIMARY KEY, status public.ground_truth_generation_status NOT NULL DEFAULT 'running', model text NOT NULL,
 prompt_version text NOT NULL, sampling_seed bigint NOT NULL, configuration jsonb NOT NULL,
 configuration_sha256 char(64) NOT NULL, prompt_sha256 char(64) NOT NULL, corpus_snapshot_sha256 char(64),
 review_bundle_sha256 char(64), safe_error text, started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz
);
ALTER TABLE public.llm_usage ADD COLUMN ground_truth_generation_run_id uuid REFERENCES public.ground_truth_generation_run(id);
ALTER TABLE public.llm_usage DROP CONSTRAINT llm_usage_single_owner;
ALTER TABLE public.llm_usage ADD CONSTRAINT llm_usage_single_owner CHECK (
 (ingestion_run_id IS NOT NULL)::integer + (evaluation_run_id IS NOT NULL)::integer +
 (ground_truth_generation_run_id IS NOT NULL)::integer <= 1);
ALTER TABLE public.llm_usage ADD COLUMN retry_count integer NOT NULL DEFAULT 0 CHECK (retry_count >= 0);

COMMIT;
