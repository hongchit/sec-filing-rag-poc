# ADR 0003: Silver source text and offsets are authoritative

## Status

Accepted

## Context

Gold search documents duplicate text and provenance for retrieval performance. The corpus reader and
citation canonicalization require exact, stable source coordinates. Depending on a denormalized
search projection would couple human verification to an index that may be rebuilt or replaced.

## Decision

Use `silver.section.text_content` and `source_start` as the section authority, and
`silver.chunk.source_start/source_end` as filing-relative chunk boundaries. Convert chunk positions by
subtracting the section start. Resolve chunk locations through silver filing, corpus, section, and
chunk relationships; do not derive them from `gold.search_document`.

## Consequences

- Reader highlights match the normalized text used for chunking.
- Gold can be rebuilt without changing citation coordinates.
- Redundant section/chunk/corpus predicates detect inconsistent relationships.
- Paragraphs can be derived without a migration, but their numbering depends on the immutable
  normalized section text.
- Extraction or normalization changes require a new compatibility version.

## Alternatives considered

- Read offsets from gold provenance: rejected because gold is a replaceable projection.
- Persist reader paragraphs: rejected because they are deterministic and derivable.
- Fuzzy-match chunk text in the full Item: rejected because exact offsets already exist and fuzzy
  matching can select the wrong repeated passage.
