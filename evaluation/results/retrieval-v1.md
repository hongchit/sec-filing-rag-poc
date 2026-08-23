# Retrieval evaluation

- Dataset SHA-256: `16758fdf6a1ab74b06772244ae8217f4530f006fb4aabfc78accee76ba06ad10`
- Configuration SHA-256: `59016d8818da6895f27ced84c86b61fba0d2165782e0b4b3e0c9c1cf3bcd595b`
- Course commit: `bc7b6aad6b92a5611d3d37bf7521a363f3b9d398`
- Selected default: `{"alpha": 0.25, "candidate_count": 10, "rrf_k": 60, "strategy": "weighted_hybrid", "top_k": 10}`
- Coverage warnings: `[]`
- Reproduce: `uv run sec-rag-evaluate-retrieval --dataset evaluation/retrieval-v1.jsonl --manifest evaluation/retrieval-v1-manifest.json`

The selected configuration maximized MRR, then Hit Rate, then lower median latency, then strategy simplicity. See the adjacent JSON for per-question rankings and failures.
