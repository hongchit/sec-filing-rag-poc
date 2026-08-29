# Architecture decisions

Architecture decision records (ADRs) preserve the context and consequences of choices that affect
multiple features or future compatibility. Current behavior remains authoritative in the feature and
reference guides; ADRs explain why that behavior exists.

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-application-owned-policy.md) | FastAPI owns business policy; Kestra carries references only | Accepted |
| [0002](0002-versioned-corpus-activation.md) | Corpora are immutable versions with one movable active pointer | Accepted |
| [0003](0003-silver-source-offset-authority.md) | Silver text and offsets are authoritative for source context | Accepted |
| [0004](0004-benchmark-selected-retrieval.md) | Retrieval defaults are promoted through reviewed benchmarks | Accepted |

New ADRs use the next four-digit number and these sections: `Status`, `Context`, `Decision`,
`Consequences`, and `Alternatives considered`. Do not rewrite accepted history to make a later choice
look original; supersede it with a new ADR and links in both records.
