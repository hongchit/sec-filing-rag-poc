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
  RELEVANT: 'Relevant',
  PARTLY_RELEVANT: 'Partly relevant',
  NON_RELEVANT: 'Non-relevant',
};

export type GenerationPromptSummary = {
  id: string;
  official_rank: number;
  selected: boolean;
  promoted: boolean;
  eligible: boolean;
  mean_score: number;
  relevant_count: number;
  partly_relevant_count: number;
  non_relevant_count: number;
  failures: number;
  valid_citation_handles: number;
  citation_handles: number;
  cross_corpus_citations: number;
  median_latency_ms: number | null;
  generation_cost_per_answer_usd: string | null;
  judge_cost_per_answer_usd: string | null;
};
export type GenerationSummary = {
  run: Record<string, unknown>;
  selected_prompt_id: string | null;
  promoted_prompt_id: string | null;
  prompts: GenerationPromptSummary[];
  availability: {
    artifact_loaded: boolean;
    audit_record_available: boolean;
    evidence_available: boolean;
  };
  warnings: Array<{ code: string; message: string; recovery_docs?: string[] }>;
  lineage: Record<string, unknown>;
};
export type GenerationMatrixResult = {
  prompt_id: string;
  label: 'RELEVANT' | 'PARTLY_RELEVANT' | 'NON_RELEVANT' | null;
  failure: string | null;
  citations_valid: boolean;
  latency_ms: number | null;
};
export type GenerationMatrixCase = {
  id: string;
  question: string;
  ticker: string;
  items: string[];
  goal: string;
  query_type: string;
  results: GenerationMatrixResult[];
};
export type GenerationCases = {
  cases: GenerationMatrixCase[];
  facets: { tickers: string[]; items: string[]; goals: string[]; query_types: string[] };
  warnings: Array<{ message: string }>;
};
export type GeneratedParagraph = { text: string; kind: string; citations: string[] };
export type GenerationCaseResult = {
  prompt_id: string;
  answer: {
    paragraphs: GeneratedParagraph[];
    limitations: string[];
    insufficient_evidence: boolean;
    disposition: string;
    policy_refusal: boolean;
  } | null;
  citation_audit: {
    citation_handles: number;
    valid_citation_handles: number;
    invalid_handles: string[];
    cross_corpus_citations: number;
  };
  judge: { label: 'RELEVANT' | 'PARTLY_RELEVANT' | 'NON_RELEVANT'; explanation: string } | null;
  generation_latency_ms: number | null;
  generation_usage: { input_tokens: number; output_tokens: number; total_tokens: number } | null;
  judge_usage: { input_tokens: number; output_tokens: number; total_tokens: number } | null;
  failure: string | null;
};
export type GenerationQuestion = {
  question: Omit<EvaluationCase, 'outcome' | 'first_relevant_rank' | 'expected' | 'retrieved'>;
  results: GenerationCaseResult[];
  expected: Chunk[];
  retrieved: Chunk[];
  evidence_available: boolean;
  warnings: Array<{ message: string }>;
};
