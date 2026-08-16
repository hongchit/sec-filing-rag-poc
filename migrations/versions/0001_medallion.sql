BEGIN;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TYPE public.resolution_status AS ENUM ('pending','resolved','failed');
CREATE TYPE public.run_status AS ENUM ('pending','running','succeeded','failed','skipped');
CREATE TYPE public.stage_status AS ENUM ('pending','running','succeeded','failed','skipped');
CREATE TYPE public.coverage_status AS ENUM ('present','legitimately_absent','failed','not_assessed');
CREATE TYPE public.corpus_lifecycle AS ENUM ('building','ready','failed','retired');
CREATE TYPE public.usage_status AS ENUM ('reported','unavailable','failed');

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
CREATE TABLE public.ingestion_run (
  id uuid PRIMARY KEY, company_id uuid NOT NULL REFERENCES public.company(id), requested_item text NOT NULL,
  trigger text NOT NULL CHECK (trigger IN ('manual','schedule','api','test')), compatibility_key char(64) NOT NULL,
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

CREATE TABLE bronze.sec_ticker_snapshot (
  id uuid PRIMARY KEY, payload jsonb NOT NULL, source_url text NOT NULL, user_agent_hash char(64) NOT NULL,
  fetched_at timestamptz NOT NULL, http_status integer NOT NULL, etag text, last_modified text, sha256 char(64) NOT NULL UNIQUE
);
CREATE TABLE bronze.sec_submission (
  id uuid PRIMARY KEY, cik text NOT NULL, payload jsonb NOT NULL, source_url text NOT NULL, user_agent_hash char(64) NOT NULL,
  fetched_at timestamptz NOT NULL, http_status integer NOT NULL, etag text, last_modified text, sha256 char(64) NOT NULL UNIQUE
);
CREATE TABLE bronze.sec_document (
  id uuid PRIMARY KEY, cik text NOT NULL, accession text NOT NULL, document_name text NOT NULL, source_url text NOT NULL,
  content bytea NOT NULL, media_type text NOT NULL, content_length bigint NOT NULL CHECK (content_length >= 0),
  user_agent_hash char(64) NOT NULL, fetched_at timestamptz NOT NULL, http_status integer NOT NULL,
  etag text, last_modified text, sha256 char(64) NOT NULL UNIQUE
);

CREATE TABLE silver.filing (
  id uuid PRIMARY KEY, company_id uuid NOT NULL REFERENCES public.company(id), ticker_snapshot_id uuid NOT NULL REFERENCES bronze.sec_ticker_snapshot(id),
  submission_id uuid NOT NULL REFERENCES bronze.sec_submission(id), document_id uuid NOT NULL REFERENCES bronze.sec_document(id),
  cik text NOT NULL, accession text NOT NULL, form text NOT NULL CHECK (form = '10-K'), primary_document text NOT NULL,
  filing_date date NOT NULL, report_date date, source_url text NOT NULL, UNIQUE (cik, accession)
);
CREATE TABLE silver.corpus_version (
  id uuid PRIMARY KEY, filing_id uuid NOT NULL REFERENCES silver.filing(id), ingestion_run_id uuid NOT NULL REFERENCES public.ingestion_run(id),
  compatibility_key char(64) NOT NULL, parser_version text NOT NULL, chunking_version text NOT NULL,
  embedding_model text NOT NULL, embedding_dimensions integer NOT NULL CHECK (embedding_dimensions > 0), index_version text NOT NULL,
  status public.corpus_lifecycle NOT NULL DEFAULT 'building', created_at timestamptz NOT NULL DEFAULT now(), ready_at timestamptz,
  UNIQUE (filing_id, compatibility_key)
);
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
  ingestion_run_id uuid NOT NULL REFERENCES public.ingestion_run(id), active boolean NOT NULL DEFAULT true,
  activated_at timestamptz NOT NULL DEFAULT now(), deactivated_at timestamptz,
  CHECK ((active AND deactivated_at IS NULL) OR (NOT active AND deactivated_at IS NOT NULL))
);
CREATE UNIQUE INDEX one_active_corpus_per_company ON public.corpus_activation(company_id) WHERE active;

CREATE FUNCTION bronze.reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'bronze tables are insert-only'; END $$;
CREATE TRIGGER sec_ticker_snapshot_immutable BEFORE UPDATE OR DELETE ON bronze.sec_ticker_snapshot FOR EACH ROW EXECUTE FUNCTION bronze.reject_mutation();
CREATE TRIGGER sec_submission_immutable BEFORE UPDATE OR DELETE ON bronze.sec_submission FOR EACH ROW EXECUTE FUNCTION bronze.reject_mutation();
CREATE TRIGGER sec_document_immutable BEFORE UPDATE OR DELETE ON bronze.sec_document FOR EACH ROW EXECUTE FUNCTION bronze.reject_mutation();

CREATE VIEW gold.corpus_status AS
SELECT c.ticker, cv.id AS corpus_version_id, f.accession, f.filing_date, s.item, s.coverage_status,
       count(DISTINCT ch.id)::integer AS chunk_count, count(DISTINCT gd.chunk_id)::integer AS search_document_count,
       COALESCE((SELECT max(lu.usage_status::text) FROM public.llm_usage lu WHERE lu.ingestion_run_id = cv.ingestion_run_id), 'unavailable') AS embedding_usage_status,
       cv.embedding_model, cv.embedding_dimensions, ca.activated_at,
       (SELECT max(ir.finished_at) FROM public.ingestion_run ir WHERE ir.company_id = c.id AND ir.status = 'succeeded') AS latest_successful_ingestion
FROM public.corpus_activation ca JOIN public.company c ON c.id = ca.company_id
JOIN silver.corpus_version cv ON cv.id = ca.corpus_version_id JOIN silver.filing f ON f.id = cv.filing_id
JOIN silver.section s ON s.corpus_version_id = cv.id LEFT JOIN silver.chunk ch ON ch.section_id = s.id
LEFT JOIN gold.search_document gd ON gd.chunk_id = ch.id WHERE ca.active
GROUP BY c.id, c.ticker, cv.id, f.accession, f.filing_date, s.item, s.coverage_status, ca.activated_at;

COMMIT;
