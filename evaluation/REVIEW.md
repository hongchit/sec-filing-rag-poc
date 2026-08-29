# Retrieval ground-truth preparation and review

This guide is the operator workflow for preparing SEC corpora, generating candidate questions, reviewing them, finalizing the retrieval ground truth, and running the retrieval evaluation. Run commands from the repository root.

For the benchmark model, retrieval strategies, metric definitions, and promotion rationale, read
[Evaluation](../docs/evaluation.md). This runbook intentionally concentrates on commands, review
decisions, artifact validation, and operational completion criteria.

## Purpose and completion criteria

The aim is to create a reproducible, human-reviewed retrieval benchmark and use it to select the best measured retrieval configuration. Ground truth in this process is not a generated answer. It is a reviewed investor question linked to one or more filing chunk IDs that retrieval should return. The benchmark measures whether those relevant chunks are found and how highly they rank.

The process has three distinct outcomes:

| Stage | Objective | Authoritative outcome |
| --- | --- | --- |
| Generate and review | Produce useful questions from substantive, correctly attributed filing passages and record human acceptance decisions | `evaluation/ground-truth-review-v1.json` |
| Finalize | Convert accepted questions into immutable retrieval cases with checksums, lineage, coverage, and warnings | `evaluation/retrieval-v1.jsonl` and `evaluation/retrieval-v1-manifest.json` |
| Evaluate | Compare retrieval strategies against the same reviewed cases and select the best measured configuration | `evaluation/results/retrieval-v1.json` and `evaluation/results/retrieval-v1.md` |

### Accepted retrieval-v1 baseline

The retrieval-v1 benchmark is accepted as the application default. Its dataset
SHA-256 is
`16758fdf6a1ab74b06772244ae8217f4530f006fb4aabfc78accee76ba06ad10`.
The 96 reviewed questions cover AAPL, MSFT, and NVDA; all five research goals;
all six required Items; both query types; and legal and non-legal risk cases.
The manifest and result contain no coverage warnings or execution failures.

The selected configuration is weighted hybrid with `candidate_count=10`,
`top_k=10`, and `alpha=0.25`. It achieved MRR `0.9395424836601307`, Hit Rate
`1.0`, zero misses, and median retrieval latency of approximately `7.38 ms`.
Eleven cases returned their first relevant chunk below rank one; their
per-question rankings remain in the result JSON for regression review. This
configuration is accepted because it follows the documented selection order,
provides complete measured recall at top ten, and has complete benchmark
coverage without warnings. A benchmark rerun is required when its corpus,
ground truth, embedding contract, retrieval grid, or retrieval logic changes.

An operationally successful end-to-end run therefore requires all of the following:

- ground-truth generation and strict review validation succeed;
- finalization produces at least one checksum-valid reviewed case whose source chunks still exist in the declared ready corpora;
- `sec-rag-evaluate-retrieval --validate-only` reports `status: valid`;
- the full evaluation reports `status: succeeded`, writes both result artifacts, and records a successful database audit row;
- the operator reviews coverage warnings, per-question misses, MRR, Hit Rate, and latency before accepting the selected default.

A command succeeding proves processing integrity, not benchmark quality. A small or unrepresentative dataset can be valid while producing misleadingly strong metrics. Treat complete target coverage, credible human review, and failure analysis as part of completion.

## 1. Prepare the environment

Before downloading filings, make sure `.env` contains real values for `DATABASE_URL`, `OPENAI_API_KEY`, `EDGAR_IDENTITY`, the ingestion token, and the Kestra credentials. `EDGAR_IDENTITY` must identify the application and a real contact. Keep the configured SEC caution mode and rate limit.

Start the Dev Container and application API as described in [Local development](../docs/local-development.md). The application API must be reachable by Kestra at `http://app:8000`. Import or re-import the sole ingestion flow, `workflows/filing_batch.yaml`, in the Kestra UI at <http://127.0.0.1:18082>.

Confirm that the database schema and API are ready:

```bash
# Apply the current application schema.
uv run sec-rag-migrate

# Start FastAPI on the address used by local clients.
uv run uvicorn sec_filing_rag.main:app --host 0.0.0.0 --port 8000

# Confirm process and database readiness.
curl -fsS http://127.0.0.1:8000/api/health
```

The health response should report both the process and application database as ready. Corpus preparation calls OpenAI for embeddings and can incur provider cost. Ground-truth generation also calls the configured generation model.

## 2. Download and prepare the first corpus for each company

Submit the latest original 10-K for every enabled company through the public API. It persists a batch and starts `sec_filings.ingestion.filing_batch`:

```bash
# Prepare the latest original 10-K for every enabled company.
curl --fail-with-body -i -X POST http://127.0.0.1:8000/api/filing-batches \
  -H 'Content-Type: application/json' -d '{}'
```

Save `batch_id` from the HTTP 202 response and poll `GET /api/filing-batches/{batch_id}` until terminal. Expect one ordered item per enabled company. A new filing succeeds; repeated latest processing skips when already active and must not duplicate corpus data.

Inspect readiness without exposing filing text or credentials:

```bash
# Confirm each company's active and historical corpus status.
curl -fsS http://127.0.0.1:8000/api/companies/AAPL/status

curl -fsS http://127.0.0.1:8000/api/companies/MSFT/status

curl -fsS http://127.0.0.1:8000/api/companies/NVDA/status

# Confirm the submitted batch reached a terminal state.
curl -fsS http://127.0.0.1:8000/api/filing-batches/$BATCH_ID

# Compare active Item coverage with silver and gold document counts.
psql "$DATABASE_URL" -c "select ticker,accession,item,coverage_status,chunk_count,search_document_count,embedding_usage_status from gold.corpus_status order by ticker,item"
```

Each company must have an active, ready default corpus. Its six Item coverage rows must be complete, and chunk and search-document counts must agree for present Items. The three active defaults also establish the parser, chunker, embedding model, and embedding-dimension contract used by ground-truth generation. Generation stops if those contracts differ.

## 3. Download and prepare more filing years

Ground-truth generation uses every ready filing compatible with the active defaults, not just the latest year. Prepare the years wanted in the evaluation pool before generating the review bundle.

Submit each desired fiscal year directly. Exact-year selection uses the SEC report date and skips a company if no original 10-K exists; it never substitutes a neighboring year:

```bash
# Prepare the exact 2024 report year for the evaluation companies.
curl --fail-with-body -i -X POST http://127.0.0.1:8000/api/filing-batches \
  -H 'Content-Type: application/json' \
  -d '{"tickers":["AAPL","MSFT","NVDA"],"fiscal_year":2024}'
```

For one company, the retained convenience route creates the same one-item batch:

```bash
# Prepare one company's exact report year through the convenience route.
curl --fail-with-body -i -X POST http://127.0.0.1:8000/api/companies/AAPL/filing-preparations \
  -H 'Content-Type: application/json' \
  -d '{"fiscal_year":2024}'
```

Poll the returned batch until every item is terminal, then inspect the company and ready corpora:

```bash
# Confirm the company's active and historical corpora.
curl -fsS http://127.0.0.1:8000/api/companies/AAPL/status

# Confirm exact-year batch completion and any skips.
curl -fsS http://127.0.0.1:8000/api/filing-batches/$BATCH_ID

# Inspect every ready corpus and its processing contract.
psql "$DATABASE_URL" -c "select c.ticker,f.report_date,f.accession,cv.id as corpus_version_id,cv.status,cv.parser_version,cv.chunking_version,cv.embedding_model,cv.embedding_dimensions from silver.corpus_version cv join silver.filing f on f.id=cv.filing_id join public.company c on c.id=f.company_id where cv.status='ready' order by c.ticker,f.report_date,f.accession,cv.created_at"
```

Exact-year processing does not replace the latest default pointer. If multiple ready processing versions exist for one accession, generation uses only the newest compatible version. A ready corpus with no usable chunks is retained in snapshot lineage and contributes zero candidates.

## 4. Generate the review bundle

Review the tracked inputs before spending model tokens:

- `config/ground-truth.json` controls model, seed, workers, target chunks, generated questions, and the five-candidate screening budget.
- `evaluation/prompts/investor-questions-v1.txt` defines meaningfulness and question-generation behavior.
- The active defaults must share one processing contract.

Generate a new bundle:

```bash
# Generate a new model-assisted ground-truth review bundle.
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

The generation run and its model usage are also auditable in PostgreSQL:

```sql
-- Inspect ground-truth generation identity, lineage, and terminal outcome.
  select id,status,model,prompt_version,sampling_seed,configuration_sha256,prompt_sha256,
         corpus_snapshot_sha256,review_bundle_sha256,safe_error,started_at,finished_at
    from public.ground_truth_generation_run
order by started_at desc;

-- Inspect model usage and retry outcomes for those generation runs.
  select ground_truth_generation_run_id,operation,model,input_tokens,output_tokens,total_tokens,
         latency_ms,usage_status,normalized_status,retry_count
    from public.llm_usage
   where ground_truth_generation_run_id is not null
order by ground_truth_generation_run_id;
```

For a successful generation, expect `ground_truth_generation_run.status = 'succeeded'`, populated snapshot and review-bundle checksums, `safe_error is null`, and a non-null `finished_at`. A failed generation has `status = 'failed'`; use `safe_error`, the diagnostic artifact, and associated `llm_usage.normalized_status` to distinguish corpus/configuration failures from model-call failures. Token usage may be `unavailable` without making an otherwise successful generation invalid.

To reuse an existing compatible bundle without repeating model calls:

```bash
# Reuse a compatible review bundle without repeating model calls.
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
# Validate structure while allowing unfinished human decisions.
uv run sec-rag-generate-ground-truth validate-review --allow-pending
```

After every decision is complete, run the strict review gate:

```bash
# Require every chunk and question decision to be complete and valid.
uv run sec-rag-generate-ground-truth validate-review
```

Expect `status: valid`, counts, and any generation shortfall warnings. Validation fails for modified generation metadata, a modified corpus snapshot, duplicate chunks, an invalid generation summary, or remaining pending decisions.

## 6. Finalize the reviewed dataset

Finalize only after strict review validation succeeds:

```bash
# Convert accepted review decisions into checksum-bound evaluation artifacts.
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
# Count finalized evaluation cases.
wc -l evaluation/retrieval-v1.jsonl

# Pretty-print the manifest for lineage, coverage, and warning review.
python -m json.tool evaluation/retrieval-v1-manifest.json
```

Each JSONL line is one accepted evaluation case. Its `question`, `query_type`, `goal`, company/corpus lineage, `allowed_items`, and `relevant_chunk_ids` define what will be queried and which retrieved chunks count as correct. The manifest is the summary and reproducibility contract: inspect `coverage`, `warnings`, `dataset_sha256`, `review_bundle_sha256`, processing versions, embedding contract, and `corpora`.

Finalization does not create a separate database run. Its success is established by the command's `status: finalized` response, the two artifacts, their checksum agreement, and a subsequent successful `--validate-only` run. Do not confuse `ground_truth_generation_run` with finalization or retrieval evaluation: it audits model-assisted candidate generation only.

Do not hand-edit the finalized JSONL or manifest. Any change breaks the manifest checksum. Make corrections in the review bundle and run `finalize` again.

## 7. Validate and run retrieval evaluation

Validate the dataset, manifest, retrieval embedding contract, and live database lineage without running the benchmark grid:

```bash
# Check dataset, manifest, embedding contract, and live lineage without benchmarking.
uv run sec-rag-evaluate-retrieval --validate-only
```

Expect `status: valid`, the case count, coverage counts, and warnings. Any non-empty reviewed dataset is valid for evaluation, so fewer than 30 cases or incomplete categorical coverage does not stop execution.

Run the full retrieval evaluation:

```bash
# Execute the complete configured retrieval benchmark grid.
uv run sec-rag-evaluate-retrieval
```

The evaluator embeds each question once, evaluates the configured keyword, vector, weighted-hybrid, and RRF grid, and computes Hit Rate, MRR, and median retrieval latency. It selects a default by MRR, then Hit Rate, lower latency, and finally strategy simplicity. Expect:

- `evaluation/results/retrieval-v1.json` with configurations, metrics, per-question rankings, selected default, coverage, and warnings;
- `evaluation/results/retrieval-v1.md` with a concise reproducibility summary.

Coverage warnings qualify how representative the benchmark is; they do not change the metric formulas. Compare results only when the dataset checksum and retrieval configuration checksum are understood.

### Inspect the evaluation outcome

The JSON result is authoritative. For every tested configuration, `results` contains:

- `hit_rate`: the fraction of questions for which at least one relevant chunk appears in the configured top-k results; `1.0` means every case had a hit;
- `mrr`: mean reciprocal rank of the first relevant chunk; `1.0` means the first result was relevant for every case, while lower values indicate later rankings or misses;
- `median_latency_ms`: median database retrieval time per question for that configuration; lower is better after quality is acceptable;
- `questions`: per-case retrieved chunk IDs, `hit`, and `reciprocal_rank`, which identify the exact misses and weak rankings;
- `selected_default`: the winner chosen by MRR, then Hit Rate, then lower latency, then strategy simplicity;
- `failures`, `coverage`, and `warnings`: execution failures and qualifications on representativeness.

Use the following database query to confirm run status and correlate it with the result artifact's `evaluation_run_id`:

```sql
-- Confirm evaluation status, checksums, selected configuration, and timing.
  select id,status,dataset_sha256,configuration_sha256,selected_configuration,
         safe_error,started_at,finished_at
    from public.retrieval_evaluation_run
order by started_at desc;

-- Inspect embedding usage and normalized provider outcomes for evaluation runs.
  select evaluation_run_id,operation,model,input_tokens,total_tokens,latency_ms,
         usage_status,normalized_status
    from public.llm_usage
   where evaluation_run_id is not null
order by evaluation_run_id;
```

A successful run has `status = 'succeeded'`, a populated `selected_configuration`, `safe_error is null`, a non-null `finished_at`, an empty artifact `failures` list, and both result files. A failed run has `status = 'failed'` and a bounded `safe_error`; result files are not written because artifact output occurs only after the benchmark finishes. Failed runs and their usage rows are retained as audit history and should not be deleted merely to rerun the benchmark.

### Decide whether the results are good enough

The software intentionally enforces no universal metric cutoff. Judge fitness using all of these checks:

1. **Ground-truth credibility:** accepted questions are natural investor questions, their relevant chunks contain sufficient evidence, and rejected boilerplate or malformed passages did not enter the dataset.
2. **Representativeness:** the manifest has at least 30 questions and covers all three companies, five goals, six required Items, both query types, and legal and non-legal risk questions. Explain any warning before using the winner as a default.
3. **Retrieval quality:** prioritize high MRR because the first useful chunk should rank early, then high Hit Rate. Inspect every case with `hit = 0` and low reciprocal rank; aggregate scores alone can hide systematic failures by company, Item, goal, or query type.
4. **Strategy evidence:** compare keyword, vector, weighted hybrid, and RRF on the same dataset and configuration checksum. Confirm the selected default's advantage is meaningful and not caused by a narrow dataset or a few duplicate/easy questions.
5. **Operational quality:** consider latency only after relevance is acceptable. Re-run comparisons when database load is comparable, because the benchmark records retrieval latency but does not isolate all environmental variance.

MRR and Hit Rate near `1.0` are strong on the reviewed dataset, but they are not proof of general production quality. High scores should prompt a check for overly literal questions, duplicated questions, source leakage, or too-small coverage. Low scores should be traced through the per-question rankings before changing retrieval configuration; the cause may instead be incorrect ground truth, missing corpus coverage, or poor question quality.

Record the accepted dataset checksum, retrieval configuration checksum, selected default, coverage warnings, and the rationale for accepting or rejecting the run. Results from different checksums are different experiments and should not be treated as direct regressions without explaining the changed inputs.

## 8. Typical correction loop

If review or evaluation reveals a weak question, edit its source entry in `evaluation/ground-truth-review-v1.json`, complete all decisions, and repeat:

```bash
# Revalidate corrected human review decisions.
uv run sec-rag-generate-ground-truth validate-review

# Rebuild finalized dataset and manifest artifacts.
uv run sec-rag-generate-ground-truth finalize

# Check the rebuilt artifacts before spending on a benchmark.
uv run sec-rag-evaluate-retrieval --validate-only

# Rerun retrieval configurations against the corrected dataset.
uv run sec-rag-evaluate-retrieval
```

If more coverage is needed, prepare additional compatible historical years, run a fresh `generate`, review the new bundle, and finalize again. Adding corpus data changes the snapshot, so an older bundle cannot be resumed against the expanded pool.
