# Glossary

- **SEC**: US Securities and Exchange Commission, source of filing metadata and documents.
- **RAG**: retrieval-augmented generation; here the implemented foundation is retrieval corpus preparation and evaluation.
- **Kestra**: workflow engine that retries and sequences reference-only callbacks.
- **Batch state**: `submitted`, `running`, `succeeded`, `partial_failure`, or `failed`.
- **Item state**: `pending`, `selecting`, `acquiring`, `processing`, then `succeeded`, `skipped`, or `failed`.
- **Acquisition**: persisted, validated EdgarTools company/filing metadata plus exact HTML bytes and checksum.
- **Snapshot**: immutable bronze representation of provider metadata or document bytes.
- **Filing**: normalized silver identity for one original 10-K accession.
- **Corpus version**: one processing-compatible set of sections, chunks, and search documents for a filing.
- **Compatibility key**: SHA-256 over parser, chunker, embedding model/dimensions, index version, and source checksum.
- **Activation/default corpus**: the sole company corpus selected for normal retrieval; historical ready corpora need not be active.
- **Section coverage**: `present`, `legitimately_absent`, `failed`, or `not_assessed` for each required Item.
- **Chunk**: deterministic bounded text segment with document-relative offsets, checksum, ordinal, and citation handle.
- **Search document**: gold retrieval row containing chunk text, lexical representation, vector, and provenance.
- **Provenance**: redundant source identity, checksum, offsets, anchor, and provider snapshot identifiers used for citation and validation.
- **Retrieval strategies**: keyword BM25, vector similarity, weighted hybrid, and reciprocal-rank fusion (RRF).
- **Ground truth**: human-reviewed questions mapped to exact relevant chunk IDs and corpus lineage for evaluation.
