# Corpus pipeline

## Preconditions and selection

A public submission first loads `config/companies.yaml` into `configuration_version`/`company`, then atomically creates `filing_batch` and ordered `filing_batch_item` rows. Latest mode chooses the maximum original 10-K by report date, filing date, and accession. Exact-year mode matches only `report_date.year`; a miss updates the item to `skipped`. Selection writes `selected_accession` and moves the item through `selecting` to `acquiring`.

## Acquisition and source validation

EdgarTools revalidates the selected accession, required metadata, original form, HTML type, and byte limit. `bronze.filing_acquisition` stores primitive provider payload JSON, exact UTF-8 content, byte length, SHA-256, company, and accession; the item stores only `acquisition_id`. Processing reloads that record and verifies `text/html` and checksum before computing the source-bound compatibility key. `ingestion_run` changes from provisional to exact key, and `ingestion_stage` records `source-validation` counts/times/failure.

Compatibility lookup joins `silver.filing` and ready `silver.corpus_version` on company, accession, and key. Exact-year reuse records a skipped run and never activates. Latest reuse skips when already active; otherwise it transactionally deactivates the old pointer, adds `corpus_activation`, and reports a successful `promoted` disposition without embedding.

## Extraction, chunking, and embedding

BeautifulSoup removes script/style/active containers, hidden elements, comments, controls, and bidirectional formatting; NFKC normalization and configured narrative limits apply before offsets are calculated. The parser extracts exactly Items 1, 1A, 3, 7, 7A, and 8. Each `silver.section` outcome is `present`, explicitly `legitimately_absent` with a reason, or an unusable failure. Any failed/not-assessed required Item prevents persistence/activation.

Present text is deterministically split by character size/overlap. A chunk ID hashes accession, Item, ordinal, chunking/compatibility version, offsets, and text checksum. OpenAI receives only chunk text; vector count and dimensions must match. `llm_usage` records model, token availability, latency, and normalized outcome. The `extraction` and `embedding` stages retain input/output counts and safe errors.

## Transactional persistence and lineage

The `persistence` transaction upserts checksum-addressed `bronze.edgar_company_snapshot`, `bronze.edgar_filing_snapshot`, and `bronze.edgar_filing_document`; links them through `silver.filing`; inserts `silver.corpus_version`; writes six `silver.section` rows and their `silver.chunk` rows; and writes one `gold.search_document` per chunk. Search provenance carries ticker, CIK, accession, Item, primary document/source URL, both source checksum names, bronze snapshot/document UUIDs, EdgarTools version, offsets, anchor, and ordinal.

Before ready status, validation requires exactly six coverage rows, no unusable coverage, chunks for present sections, no chunks plus a reason for absent sections, matching silver/gold counts and text/citations, correct embedding model/dimensions, required provenance keys, and matching offsets/anchors. Only then is `silver.corpus_version.status` set to `ready`. Latest mode replaces the default in the same transaction; exact-year mode leaves it unactivated. `ingestion_run` receives final counts and status.

Uniqueness on snapshot/document checksums, filing CIK/accession, filing/compatibility, section Item, chunk ordinal/citation, and search chunk ID makes retries idempotent. A failure records a safe terminal run/stage error; transactional candidate work rolls back and the prior ready/default corpus remains available.
