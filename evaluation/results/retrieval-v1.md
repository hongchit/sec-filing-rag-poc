# Retrieval evaluation

- Dataset SHA-256: `a63a2c3c9f6ff2c0cfcb3317f3450cd04c3c26579958437a732835b699d8188f`
- Configuration SHA-256: `d8da2fe291a5cf63e3cadfca84bd2fd0ee6ff8ebe882af403b5d03c2412d8088`
- Course commit: `bc7b6aad6b92a5611d3d37bf7521a363f3b9d398`
- Selected default: `{"alpha": 0.25, "candidate_count": 50, "rrf_k": 60, "strategy": "weighted_hybrid", "top_k": 10}`
- Coverage warnings: `[]`
- Reproduce: `uv run sec-rag-evaluate-retrieval --dataset evaluation/retrieval-v1.jsonl --manifest evaluation/retrieval-v1-manifest.json`

The selected configuration maximized MRR, then Hit Rate, then lower median latency, then strategy simplicity. See the adjacent JSON for per-question rankings and failures.
