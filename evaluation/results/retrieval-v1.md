# Retrieval evaluation

- Dataset SHA-256: `16758fdf6a1ab74b06772244ae8217f4530f006fb4aabfc78accee76ba06ad10`
- Configuration SHA-256: `d8da2fe291a5cf63e3cadfca84bd2fd0ee6ff8ebe882af403b5d03c2412d8088`
- Course commit: `bc7b6aad6b92a5611d3d37bf7521a363f3b9d398`
- Selected default: `{"alpha": 0.25, "candidate_count": 10, "rrf_k": 60, "strategy": "weighted_hybrid", "top_k": 10}`
- Coverage warnings: `[]`
- Reproduce: `uv run sec-rag-evaluate-retrieval --dataset evaluation/retrieval-v1.jsonl --manifest evaluation/retrieval-v1-manifest.json`

The selected configuration maximized MRR, then Hit Rate, then lower median latency, then strategy simplicity. See the adjacent JSON for per-question rankings and failures.
