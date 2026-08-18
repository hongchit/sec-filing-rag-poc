# Retrieval ground-truth preparation and review

This guide is the developer workflow for preparing SEC corpora, generating candidate questions, reviewing them, finalizing the retrieval ground truth, and running the retrieval evaluation. Run commands from the repository root.

## 1. Prepare the environment

Before downloading filings, make sure `.env` contains real values for `DATABASE_URL`, `OPENAI_API_KEY`, `EDGAR_IDENTITY`, the ingestion token, and the Kestra credentials. `EDGAR_IDENTITY` must identify the application and a real contact. Keep the configured SEC caution mode and rate limit.

Start the Dev Container, application API, and frontend as described in the main README. The application API must be reachable by Kestra at `http://app:8000`. Import or re-import these flows in the Kestra UI at <http://127.0.0.1:18082>:

- `workflows/ingest_corpus.yaml`
- `workflows/prepare_historical_filing.yaml`

Confirm that the database schema and API are ready:

```bash
uv run sec-rag-migrate
uv run uvicorn sec_filing_rag.main:app --host 0.0.0.0 --port 8000
curl -fsS http://127.0.0.1:8000/api/health
```

The health response should report both the process and application database as ready. Corpus preparation calls OpenAI for embeddings and can incur provider cost. Ground-truth generation also calls the configured generation model.

## 2. Download and prepare the first corpus for each company

In Kestra, run `sec_filings.ingestion.ingest_corpus` with `target=all`. This downloads and prepares the latest original 10-K for every enabled company. To prepare only one company, run it with `target=AAPL`, `target=MSFT`, or `target=NVDA`.

Kestra is the supported entry point for scheduled and operator-initiated ingestion. The protected callback below is useful only in automated tests and local callback diagnostics; do not use it as the normal operator workflow:

```bash
curl -fsS -X POST http://127.0.0.1:8000/internal/ingestions \
  -H "Authorization: Bearer $INGESTION_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"target":"all","trigger":"manual"}'
```

Expect one result per enabled company. A new filing should report `outcome: succeeded` and a ready corpus disposition. Repeating unchanged ingestion should report `outcome: skipped`; it must not create duplicate corpus data.

Inspect readiness without exposing filing text or credentials:

```bash
curl -fsS http://127.0.0.1:8000/api/companies/AAPL/status
curl -fsS http://127.0.0.1:8000/api/companies/MSFT/status
curl -fsS http://127.0.0.1:8000/api/companies/NVDA/status
psql "$DATABASE_URL" -c "select ticker,accession,item,coverage_status,chunk_count,search_document_count,embedding_usage_status from gold.corpus_status order by ticker,item"
```

Each company must have an active, ready default corpus. Its six Item coverage rows must be complete, and chunk and search-document counts must agree for present Items. The three active defaults also establish the parser, chunker, embedding model, and embedding-dimension contract used by ground-truth generation. Generation stops if those contracts differ.

## 3. Download and prepare more filing years

Ground-truth generation uses every ready filing compatible with the active defaults, not just the latest year. Prepare the years wanted in the evaluation pool before generating the review bundle.

First discover the original 10-K for a fiscal year:

```bash
curl -fsS -X POST http://127.0.0.1:8000/api/companies/AAPL/filings/discover \
  -H 'Content-Type: application/json' \
  -d '{"period":{"granularity":"year","value":"2024"}}'
```

The response contains `exact`, `earlier`, and `later` candidates. Check the accession, report date, `ready` flag, and corpus version. If `exact` is present, submit preparation without a confirmation accession:

```bash
curl -fsS -X POST http://127.0.0.1:8000/api/companies/AAPL/filings/prepare \
  -H 'Content-Type: application/json' \
  -d '{"period":{"granularity":"year","value":"2024"}}'
```

If the requested year is missing, choose one of the displayed `earlier` or `later` candidates deliberately and send its exact accession:

```bash
curl -fsS -X POST http://127.0.0.1:8000/api/companies/AAPL/filings/prepare \
  -H 'Content-Type: application/json' \
  -d '{"period":{"granularity":"year","value":"2024"},"confirmed_accession":"ACCESSION_FROM_DISCOVERY"}'
```

The prepare endpoint returns HTTP 202 with a `request_id`, Kestra `execution_id`, and `status: submitted`. It launches `prepare_historical_filing`; preparation is asynchronous. Repeat discovery and preparation for each desired fiscal year and each ticker. Do not invent an accession or reuse one from another company.

Monitor a company until the preparation request is `succeeded` and has a `corpus_version_id`:

```bash
curl -fsS http://127.0.0.1:8000/api/companies/AAPL/status
psql "$DATABASE_URL" -c "select c.ticker,pr.requested_year,pr.selected_accession,pr.status,pr.corpus_version_id,pr.safe_error from public.preparation_request pr join public.company c on c.id=pr.company_id order by pr.created_at desc"
psql "$DATABASE_URL" -c "select c.ticker,f.report_date,f.accession,cv.id as corpus_version_id,cv.status,cv.parser_version,cv.chunking_version,cv.embedding_model,cv.embedding_dimensions from silver.corpus_version cv join silver.filing f on f.id=cv.filing_id join public.company c on c.id=f.company_id where cv.status='ready' order by c.ticker,f.report_date,f.accession,cv.created_at"
```

Historical preparation does not replace the latest default pointer. If multiple ready processing versions exist for one accession, generation uses only the newest compatible version. A ready corpus with no usable chunks is retained in snapshot lineage and contributes zero candidates.

## 4. Generate the review bundle

Review the tracked inputs before spending model tokens:

- `config/ground-truth.json` controls model, seed, workers, target chunks, generated questions, and the five-candidate screening budget.
- `evaluation/prompts/investor-questions-v1.txt` defines meaningfulness and question-generation behavior.
- The active defaults must share one processing contract.

Generate a new bundle:

```bash
uv run sec-rag-generate-ground-truth generate
```

The command writes `evaluation/ground-truth-review-v1.json`. The filename remains stable for the existing CLI, while the document's internal format version identifies compatibility. A successful command reports the selected chunk count, question count, run ID, and structured warnings.

Generation creates all 18 company/Item strata, deterministically ranks the combined multi-year candidates, and screens no more than five candidates per stratum. It retains up to two meaningful chunks and produces three questions for each retained chunk: one `exact_keyword` and two `semantic_paraphrase` questions. Zero or one selected chunk is valid.

Inspect `generation_summary` in the bundle. Every stratum reports:

- `available_chunks`: compatible chunks in all ready years;
- `screened_chunks`: candidates actually sent to the model;
- `selected_meaningful_chunks`: candidates retained for review;
- `target`: normally two;
- `source_shortfall`: fewer source chunks than the target;
- `meaningfulness_shortfall`: fewer meaningful chunks than the target.

These shortfalls are quality warnings, not failed generation. `evaluation/ground-truth-generation-failure.json` is reserved for operational or integrity failures such as missing defaults, incompatible contracts, database errors, or model failures.

To reuse an existing compatible bundle without repeating model calls:

```bash
uv run sec-rag-generate-ground-truth generate --resume
```

Resume succeeds only when the bundle format, configuration, prompt checksum, and live corpus snapshot still match. An older bundle format or changed corpus is intentionally rejected; generate a fresh bundle instead.

## 5. Review and edit the generated ground truth

Open `evaluation/ground-truth-review-v1.json` in an editor. Do not run `generate` again without `--resume` after beginning review, because a fresh generation replaces the review artifact.

For every object in `chunks`, inspect the complete `text`, citation, ticker, accession, report date, Item, offsets, source URL, and meaningfulness explanation. Decide whether the passage is a valid source of retrieval truth:

- Set the chunk's `review_status` to `accepted` when the text is substantive, correctly attributed, and suitable as the relevant retrieval passage.
- Set it to `rejected` when it is navigation, boilerplate, malformed, incorrectly classified, too ambiguous, or otherwise unsuitable.

For every question in every chunk, replace `review_status: pending` with `accepted` or `rejected`, including questions under a rejected chunk. No pending decision may remain.

Accept a question only when all of the following are true:

- it is natural and useful to an investor;
- the associated chunk contains enough evidence to answer it;
- it does not refer to “the chunk,” hidden metadata, or the generation process;
- `goal` correctly describes the research intent;
- `query_type` is correct: `exact_keyword` uses material wording likely present in the filing, while `semantic_paraphrase` expresses the need without depending on the same keywords;
- the question ends with `?` and is not a duplicate of another accepted question.

You may edit `question`, `goal`, or `query_type` before accepting it. Do not edit the question `id`, chunk ID or checksum, ticker, company, corpus version, accession, report date, Item, citation, offsets, source URL, source metadata, generation metadata, corpus snapshot, or generation summary. Those fields preserve reproducibility and lineage.

A question becomes an evaluation record only when both its parent chunk and the question have `review_status: accepted`. Rejecting a chunk excludes all of its questions even if an individual question was marked accepted. Conversely, accepting a chunk does not automatically accept all questions.

Check structure while review is still in progress:

```bash
uv run sec-rag-generate-ground-truth validate-review --allow-pending
```

After every decision is complete, run the strict review gate:

```bash
uv run sec-rag-generate-ground-truth validate-review
```

Expect `status: valid`, counts, and any generation shortfall warnings. Validation fails for modified generation metadata, a modified corpus snapshot, duplicate chunks, an invalid generation summary, or remaining pending decisions.

## 6. Finalize the reviewed dataset

Finalize only after strict review validation succeeds:

```bash
uv run sec-rag-generate-ground-truth finalize
```

Finalization rechecks accepted chunks against their exact live ready corpus and checksum, then writes:

- `evaluation/retrieval-v1.jsonl`: one reviewed evaluation case per accepted question;
- `evaluation/retrieval-v1-manifest.json`: checksums, processing contract, exact corpus lineage, coverage counts, and warnings.

At least one accepted question is required. Changed chunks, non-ready corpora, incompatible lineage, checksum changes, and an empty accepted dataset are hard failures. The following remain quality targets and produce structured manifest warnings rather than stopping finalization:

- at least 30 accepted questions;
- AAPL, MSFT, and NVDA coverage;
- all five research goals;
- Items 1, 1A, 3, 7, 7A, and 8;
- exact-keyword and semantic-paraphrase queries;
- legal/regulatory and non-legal risk coverage.

Inspect the finalized records and warnings:

```bash
wc -l evaluation/retrieval-v1.jsonl
python -m json.tool evaluation/retrieval-v1-manifest.json
```

Do not hand-edit the finalized JSONL or manifest. Any change breaks the manifest checksum. Make corrections in the review bundle and run `finalize` again.

## 7. Validate and run retrieval evaluation

Validate the dataset, manifest, retrieval embedding contract, and live database lineage without running the benchmark grid:

```bash
uv run sec-rag-evaluate-retrieval --validate-only
```

Expect `status: valid`, the case count, coverage counts, and warnings. Any non-empty reviewed dataset is valid for evaluation, so fewer than 30 cases or incomplete categorical coverage does not stop execution.

Run the full retrieval evaluation:

```bash
uv run sec-rag-evaluate-retrieval
```

The evaluator embeds each question once, evaluates the configured keyword, vector, weighted-hybrid, and RRF grid, and computes Hit Rate, MRR, and median retrieval latency. It selects a default by MRR, then Hit Rate, lower latency, and finally strategy simplicity. Expect:

- `evaluation/results/retrieval-v1.json` with configurations, metrics, per-question rankings, selected default, coverage, and warnings;
- `evaluation/results/retrieval-v1.md` with a concise reproducibility summary.

Coverage warnings qualify how representative the benchmark is; they do not change the metric formulas. Compare results only when the dataset checksum and retrieval configuration checksum are understood.

## 8. Typical correction loop

If review or evaluation reveals a weak question, edit its source entry in `evaluation/ground-truth-review-v1.json`, complete all decisions, and repeat:

```bash
uv run sec-rag-generate-ground-truth validate-review
uv run sec-rag-generate-ground-truth finalize
uv run sec-rag-evaluate-retrieval --validate-only
uv run sec-rag-evaluate-retrieval
```

If more coverage is needed, prepare additional compatible historical years, run a fresh `generate`, review the new bundle, and finalize again. Adding corpus data changes the snapshot, so an older bundle cannot be resumed against the expanded pool.
