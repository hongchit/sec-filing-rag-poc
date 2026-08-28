export type Config = {
  id: string;
  official_rank: number;
  selected: boolean;
  strategy: string;
  candidate_count: number;
  top_k: number;
  alpha: number;
  rrf_k: number;
  hit_rate: number;
  mrr: number;
  median_latency_ms: number;
};
export type Chunk = {
  chunk_id: string;
  corpus_version_id?: string;
  missing: boolean;
  rank?: number;
  matched: boolean;
  preview: string;
  citation?: string;
  ticker?: string;
  item?: string;
  accession?: string;
  source_url?: string;
};
export type FullChunk = Chunk & { text: string; provenance: unknown };
export type EvaluationCase = {
  id: string;
  question: string;
  ticker: string;
  items: string[];
  goal: string;
  query_type: string;
  accession: string;
  outcome: 'miss' | 'later_hit' | 'rank_one';
  first_relevant_rank: number | null;
  expected: Chunk[];
  retrieved: Chunk[];
};
export type Summary = {
  run: {
    status: string;
    question_count: number;
    finished_at?: string | null;
    [key: string]: unknown;
  };
  coverage: Record<string, number>;
  warnings: Array<{ message?: string }>;
  selected_default_id: string;
  strategy_best: Record<string, string>;
  configurations: Config[];
  lineage: Record<string, unknown>;
};
export type Cases = {
  configuration_id: string;
  cases: EvaluationCase[];
  facets: { tickers: string[]; items: string[]; goals: string[]; query_types: string[] };
  warnings: Array<{ message: string }>;
};
export const labels: Record<string, string> = {
  keyword: 'Keyword',
  vector: 'Vector',
  weighted_hybrid: 'Weighted hybrid',
  rrf: 'RRF',
  rank_one: 'Rank 1 hit',
  later_hit: 'Later hit',
  miss: 'Miss',
};
