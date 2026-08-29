# Glossary

- **10-K:** Annual SEC filing containing an issuer's business, risk, management, legal, market-risk,
  and financial disclosures. This project excludes amendments (`10-K/A`).
- **Accession:** SEC's stable identifier for one filing submission.
- **Activation/default corpus:** The single ready corpus selected for ordinary company retrieval.
  Other ready corpora remain historical.
- **Acquisition:** Persisted and validated EdgarTools metadata plus exact filing HTML bytes and
  checksum.
- **BM25:** Lexical ranking method that rewards query terms according to frequency in a document and
  rarity across documents. It is useful for exact filing terminology.
- **Bronze:** Immutable source snapshots and acquisition evidence.
- **Chunk:** Deterministic bounded text segment with overlap, offsets, checksum, ordinal, and citation
  handle. Retrieval ranks chunks rather than entire filings.
- **Citation handle:** Application-generated stable label connecting generated text to one chunk.
- **Compatibility key:** SHA-256 over source and processing contracts used to decide whether a ready
  corpus can be reused safely.
- **Corpus:** Searchable knowledge derived from one or more source documents. Here a corpus version
  represents one processed filing.
- **Corpus version:** One immutable processing-compatible set of sections, chunks, and search
  documents for a filing.
- **Embedding:** Numeric vector representing text meaning. Similar vectors can retrieve paraphrases
  that do not share exact words.
- **EDGAR:** SEC's Electronic Data Gathering, Analysis, and Retrieval system, the source of filings.
- **EdgarTools:** Python dependency used to resolve companies, select filings, and acquire original
  filing HTML.
- **Gold:** Replaceable retrieval projection containing lexical and vector search fields.
- **Ground truth:** Human-reviewed questions mapped to exact chunks that retrieval should return; it
  is not a generated answer.
- **Grounding:** Constraining generation to supplied evidence and validating its citations. Grounding
  improves verifiability but does not guarantee that every interpretation is correct.
- **Hit Rate:** Fraction of evaluation questions with at least one relevant result inside top-k.
- **Hybrid retrieval:** Combination of lexical and semantic retrieval. Weighted hybrid combines
  normalized scores; reciprocal-rank fusion combines positions.
- **Idempotency:** Property that makes safe repetition produce or return the same durable operation
  instead of duplicating provider work.
- **Inline XBRL:** Machine-readable financial markup embedded inside filing HTML. It creates
  realistic parsing boundaries even when the reader ultimately shows plain text.
- **Item:** Standard numbered section of a Form 10-K. The project covers Items 1, 1A, 3, 7, 7A,
  and 8.
- **Kestra:** Workflow engine that sequences and retries reference-only ingestion callbacks.
- **Large language model (LLM):** Generative model used here to synthesize structured answers and
  assist evaluation, not as the authoritative store of filing knowledge.
- **Lineage:** Identifiers and checksums connecting output to exact source, corpus, configuration,
  prompt, model, and processing versions.
- **Mean reciprocal rank (MRR):** Average of the reciprocal position of the first relevant result;
  higher values mean relevant evidence tends to appear earlier.
- **NFKC:** Unicode normalization form used before extraction so equivalent character forms share a
  consistent representation.
- **Original filing:** Exact form `10-K`, excluding amendments and neighboring report years.
- **Paragraph:** Reader projection of one non-empty normalized section source line. Paragraph indexes
  are one-based; offsets are zero-based and end-exclusive.
- **Provenance:** Redundant source identity, checksums, offsets, citation, and snapshot references
  used for verification.
- **Reciprocal-rank fusion (RRF):** Hybrid method that combines result ranks without requiring raw
  keyword and vector scores to have the same scale.
- **Retrieval-augmented generation (RAG):** Pattern that retrieves relevant knowledge before an LLM
  generates an answer, keeping source knowledge outside model weights.
- **Research goal:** Intent category that guides retrieval and generation: business, key risks,
  management analysis, market risk, or legal/regulatory risk.
- **Safe error:** Bounded application-owned explanation that excludes credentials, source bodies,
  and raw provider details.
- **Search document:** Gold row containing one chunk's text, lexical representation, vector,
  filters, citation, and provenance.
- **Section coverage:** `present`, `legitimately_absent`, `failed`, or `not_assessed` outcome for each
  required Item.
- **Server-sent events (SSE):** One-way HTTP event stream used to report research progress while
  durable server-side work continues.
- **Silver:** Normalized application authority for filings, corpus versions, sections, chunks, text,
  and offsets.
- **Snapshot:** Immutable bronze representation of provider metadata or exact document bytes.
- **Top-k:** Maximum number of highest-ranked chunks returned to the next RAG stage.
- **Vector similarity:** Retrieval based on distance between embedding vectors rather than exact word
  overlap.
- **Weighted hybrid:** Retrieval strategy combining normalized BM25 and vector scores using a
  measured weight (`alpha`).
