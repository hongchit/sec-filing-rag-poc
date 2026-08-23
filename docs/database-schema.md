# Database schema

`migrations/versions/0001_schema.sql` is the complete application schema and only migration. It is a fresh-start contract, not an upgrade. The migrator creates `public.schema_migration` and stores the file checksum.

## Public control and audit tables

`configuration_version` stores normalized company configuration and checksum. `company` stores enabled ticker identity/resolution. `filing_batch` stores latest/exact-year intent, fiscal-year constraint, request/execution correlation, aggregate state, timestamps, and safe error. `filing_batch_item` stores ordered company work, lifecycle, selected accession, acquisition/corpus references, timestamps, and safe error; `(batch_id, position)` and `(batch_id, company_id)` are unique.

`ingestion_run` records company, mode trigger (`latest`, `exact_year`, or `test`), compatibility key, Kestra execution, stage, counts, terminal state, and error. `ingestion_stage` records one attempt per named stage with counts/times. `llm_usage` can belong to at most one ingestion, retrieval-evaluation, or ground-truth-generation run and records token availability, retry count, latency, and normalized result.

`corpus_activation` is the history of default changes. Its partial unique index permits one live default per company. `retrieval_evaluation_run` and `ground_truth_generation_run` store reproducibility checksums, selected configuration, state, and safe errors.

## Bronze, silver, and gold

`bronze.filing_acquisition` is the persisted batch handoff: provider payload JSON, HTML bytes, media type, length/SHA-256, company, accession, and time. The company, filing, and document snapshot tables retain canonical lineage. Mutation triggers reject snapshot update/delete; checksum uniqueness provides replay identity.

`silver.filing` joins company to snapshots and uniquely identifies `(cik, accession)`. `corpus_version` uniquely identifies `(filing_id, compatibility_key)` and records processing/source contract. `section` has one row per corpus/Item with coverage and lineage. `chunk` stores deterministic identity, text, offsets, citation, version, and checksum.

`gold.search_document` has one row per chunk with filter keys, repeated retrieval text/citation, JSON provenance, vector contract, and lexical document. BM25 is pinned to English; B-tree indexes support company/corpus/filing/Item prefilters. `gold.corpus_status` exposes the active default's filing, coverage, counts, usage, activation, and latest successful ingestion.

There are no foreign keys to Kestra PostgreSQL. Kestra engine tables are deliberately outside this schema.
