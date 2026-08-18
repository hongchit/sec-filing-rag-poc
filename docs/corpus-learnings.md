# Corpus learnings and regression baseline

Baseline date: 2026-08-17. Acquisition dependency: `edgartools==5.41.0`.

## Retired transport findings

The application no longer owns SEC transport or discovery parsing. Supplemental-submissions filename validation, missing-recent-filing fallback, hostile Atom/index parsing, SEC host/path/row allowlists, custom XOM CIK recovery, HTTP status/header/ETag/Last-Modified behavior, and manual retry/pacing tests are retired. EdgarTools owns those concerns. There is deliberately no fallback downloader and no SEC HTTP unit-test suite; `httpx` remains only for authenticated Kestra calls.

## Retained EdgarTools contract findings

Ticker resolution fails for zero or multiple distinct CIK matches. Original selection is exact-form `10-K` and excludes `10-K/A`. Fiscal-year discovery requests a full historical load; callback accessions are rediscovered and revalidated. Accession, report date, primary document, homepage URL, filing URL, and full-text URL are mandatory. Missing or non-HTML provider documents fail closed. `Filing.html()` is deterministically encoded as UTF-8 and checksummed before parsing.

Verified resolution evidence: XOM uniquely resolves through EdgarTools to CIK `34088`. CIK `2115436` has no original 10-K; no custom recovery is required. For TSLA, amendment `0001104659-26-053166` is excluded while original `0001628280-26-003952` remains eligible.

## Retained filing-content and pipeline findings

The current EdgarTools acceptance baseline is:

- MSFT `0001193125-26-323660`: fragmented headings `ITEM 1A. RIS` / `K FACTORS`, `ITEM 3. LEGAL` / `PROCEEDINGS`, `ITEM 7A. QUANTITATIVE AND QUALITAT` / `IVE DISCLOSURES ABOUT MARKET RISK`, and `ITEM 8. FINANCIAL STATE` / `MENTS AND SUPPLEMENTARY DATA`; 8,585,501 UTF-8 bytes; SHA-256 `4bcf2da2871acc19e32c5a62f36f6d83d6aae03cdc4aaa9a86a9a21ee8223f02`.
- JPM `0001628280-26-008131`: short bounded Item 3 cross-reference; 12,927,325 UTF-8 bytes; SHA-256 `4d9febdbc2038dcdca8726053286df4cbbfd48885051cbd781efcc3becb66a23`.
- XOM `0000034088-26-000045`: six-Item extraction; 5,591,068 UTF-8 bytes; SHA-256 `3591db2246ab14c52465d32f69b459b000919c141a5656c81cf59acf0a805be8`.

Active regressions cover ambiguous or unbounded boundaries failing closed; explicit absence versus extraction failure; removal of active, hidden, comment, control, and bidi content; narrative and document limits; checksum-sensitive compatibility and chunk identities; exact six-Item coverage and provenance; non-activation of partial corpora; isolated batch failures; and non-destructive replacement with historical failures preserved.

Earlier custom-client acceptance was historical evidence only. Retrieval evaluation and ground-truth generation are implemented schema concerns, not future milestones.
