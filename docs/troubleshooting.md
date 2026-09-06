# Troubleshooting

Start with the visible symptom, then inspect the application-owned state before changing anything.
Errors are intentionally bounded, so correlate `X-Request-ID`, batch/research UUIDs, and Kestra
execution IDs across logs and database rows.

## Startup

| Symptom/event | Likely cause | Safe action |
| --- | --- | --- |
| `startup_configuration_invalid` | Placeholder, missing secret, invalid tracked file, model mismatch, or missing price | Read the issue category, correct configuration, restart |
| `startup_database_unavailable` | Bad URL, PostgreSQL unavailable, or pool timeout | Restore connectivity; do not expose the credential-bearing URL |
| `startup_schema_invalid` | Missing migration, checksum drift, or required relation absent | Run migrations; restore changed applied migrations |
| Process starts but provider call fails | SEC/OpenAI/Kestra are runtime dependencies | Inspect bounded error and provider availability/limits |

Startup never echoes supplied values. [Configuration](configuration.md) lists validation rules.

## Filing preparation and Kestra

| Symptom | Inspection | Remediation |
| --- | --- | --- |
| Batch remains `submitted` | FastAPI submission log and Kestra availability | Restore Kestra, then resubmit; failed submission marks pending items safely |
| Daily launcher returns `scheduled_ingestion_owner_unavailable` | First configured administrator has not signed in or is disabled | Sign in once with the first `GOOGLE_ADMIN_EMAILS` address or reactivate that account |
| Daily launcher fails before `filing_batch` starts | Launcher HTTP/subflow attempts and batch safe error | Restore the dependency and rerun the launcher; its execution ID prevents duplicate batch creation |
| Expected daily execution is absent | Launcher trigger state, 06:08 UTC schedule, and missed-run policy | Enable the trigger; after downtime Kestra recovers only the last missed occurrence |
| Item remains non-terminal | Kestra task attempts and batch finalization | Allow/retry finalization; it closes stranded items |
| Exact-year item is `skipped` | `safe_error` and requested report year | Expected when no original 10-K exists; do not substitute a nearby year |
| Latest batch succeeds with `skipped` items | Item ingestion runs show `stage='unchanged'` | Healthy no-change result; the compatible corpus was reused without OpenAI |
| One company fails, others continue | Item/run/stage rows | Correct that company's source/provider issue and submit a new batch |
| `401` on internal callback | Kestra secret and raw ingestion token correspondence | Re-encode the same raw token; never paste it into logs |

Kestra state does not replace application state. See [Orchestration](orchestration.md) for retry and
finalization semantics.

## Corpus processing

| Symptom | Likely cause | Action |
| --- | --- | --- |
| Source validation fails | Metadata, HTML type, size, or checksum inconsistency | Reacquire after confirming SEC/EdgarTools result |
| Item coverage is failed | Ambiguous/unbounded headings or unusable content | Inspect safe parser reason and fixture; do not activate partial corpus |
| Embedding fails | Provider, model, count, or dimensions | Align tracked/runtime contract and retry a new run |
| Compatible corpus is not reused | Source or compatibility component changed | Compare checksum/parser/chunker/model/dimensions/index version |
| Unchanged daily run shows OpenAI usage | Accession, source checksum, or compatibility key differs | Treat it as new/incompatible work and inspect the recorded key before retrying |
| Historical run changed active corpus | Policy regression | Exact-year mode must never promote; stop and investigate |

Candidate failures should preserve the previous ready/default corpus. [Pipeline](pipeline.md) owns
the compatibility and validation rules.

## Research

| Symptom | Meaning/action |
| --- | --- |
| Research appears stuck after tab closes | Streaming disconnect does not cancel work; recover by stored ID/idempotency key |
| `409` on replay | The same idempotency key was used with different input, or work is still running |
| Insufficient evidence | Request is allowed, but retrieved passages do not support a complete answer |
| Deterministic rejection message | Policy classified investment advice or unsupported scope; generated refusal was discarded |
| Usage/estimate unavailable | Provider omitted usage or request predates pricing snapshots; not necessarily a failed answer |
| Citation missing from answer | Structured validation should reject unknown/absent handles; inspect failed request logs |

## Evaluation dashboard and artifacts

| Symptom | Likely cause | Action |
| --- | --- | --- |
| Dashboard returns `404` | Current artifacts are absent | Produce/copy the accepted artifacts at configured paths |
| Dashboard returns `409` | Checksums, cases, winner, or DB run identity conflict | Validate artifacts; never hand-edit only one member of the set |
| Referenced chunk missing | Corpus/artifact drift | Restore the declared corpus or regenerate/review a new benchmark version |
| Strong average but visible weak cases | Coverage or rank distribution issue | Inspect per-question misses/later hits before promotion |

Use the [Evaluation](evaluation.md) concepts and the
[review runbook](../evaluation/REVIEW.md) for artifact correction.

## Corpus reader

| Symptom | Explanation/action |
| --- | --- |
| Reader-specific not found | Invalid ticker/Item/UUID, non-ready corpus, or inconsistent chunk relationship |
| Ticker or Item changes automatically | Corpus UUID/chunk location is authoritative and canonicalizes the route |
| Highlight disappears after deliberate navigation | Chunk highlight is intentionally session-local and clears on corpus/Item change |
| EDGAR opens at document top | Browser lacks text fragments or phrase did not match; copy paragraph text or use filing contents |
| Table text is fragmented | Reader faithfully shows indexed plain text; use original EDGAR rendering for tables |

## Useful application queries

Use these read-only queries to follow an ingestion problem from its batch-level outcome down to
individual company work, processing stages, and the active corpus. Run them against the application
database, not Kestra PostgreSQL.

### Check recent batch outcomes

Start here when a submitted preparation appears stuck, failed, or only partly successful. The query
shows the requested mode and fiscal year, the application status, the correlated Kestra execution,
and any bounded batch-level error. Recent rows appear first.

```SQL
  select id,mode,fiscal_year,status,kestra_execution_id,safe_error
    from public.filing_batch
order by created_at desc
```

Use `id` to inspect the batch through the API. Use `kestra_execution_id` to find the corresponding
workflow execution. A null execution ID on a failed batch can indicate that Kestra submission never
completed.

### Identify the affected company item

After locating a batch, inspect its ordered company work. This query reveals which item failed or
skipped, whether filing selection produced an accession, and whether processing reached a corpus
version.

```SQL
  select batch_id,position,status,selected_accession,corpus_version_id,safe_error
    from public.filing_batch_item
order by batch_id,position
```

Interpret missing references in lifecycle order: no `selected_accession` points to selection or an
expected exact-year miss; an accession without `corpus_version_id` points to acquisition or corpus
processing; a populated corpus UUID identifies the ready/reused result. Filter by `batch_id` for a
busy database.

### Find the failing processing stage

Use ingestion runs when selection succeeded but corpus preparation did not. `stage` identifies the
last processing phase, while section and chunk counts show how far usable output progressed.

```SQL
  select id,trigger,status,stage,section_count,chunk_count,safe_error
    from public.ingestion_run
order by created_at desc
```

The trigger distinguishes latest, exact-year, and test work. A ready-corpus reuse may finish without
new section or chunk counts; do not treat zero new embeddings as failure without checking status and
stage. For deeper timing/count analysis, join the run ID to `public.ingestion_stage`.

### Verify the active corpus projection

Finish by confirming what ordinary retrieval can use. This view lists every Item in each active
corpus, its coverage outcome, and the silver-chunk versus gold-search-document counts.

```SQL
  select ticker,accession,item,coverage_status,chunk_count,search_document_count
    from gold.corpus_status
order by ticker,item
```

Expect six rows per active corpus. For a present Item, `chunk_count` and `search_document_count`
should be equal and greater than zero. A legitimately absent Item should have no chunks or search
documents. Because this view covers active defaults only, use company status or the silver tables
when diagnosing a historical corpus.

Run a query from the command line by placing it in `SQL`:

```bash
# Execute the selected read-only diagnostic statement against application PostgreSQL.
psql "$DATABASE_URL" -c "$SQL"
```

Treat `DATABASE_URL` as a secret. Do not include command output containing source text, credentials,
or private data in issue reports.
