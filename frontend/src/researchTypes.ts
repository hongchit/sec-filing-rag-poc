import type { ResearchGoal } from './goals';
export type Company = { ticker: string; enabled: boolean; name?: string; corpus_status?: string };
export type Corpus = {
  corpus_version_id: string;
  accession: string;
  report_date: string;
  filing_date: string;
};
export type CompanyStatus = {
  ticker: string;
  active_corpus: Corpus | null;
  historical_corpora: Corpus[];
};
export type Evidence = {
  rank: number;
  chunk_id: string;
  corpus_version_id: string;
  citation_handle: string;
  ticker: string;
  accession: string;
  item: string;
  excerpt: string;
  source_start: number;
  source_end: number;
  source_anchor?: string;
  source_url: string;
  strategy: string;
  score: number;
};
export type Research = {
  research_id: string;
  ticker: string;
  corpus_version_id: string;
  goal: ResearchGoal;
  question: string;
  allowed_items: string[] | null;
  status: string;
  safe_error?: string;
  answer?: { text: string; kind: 'filing_fact' | 'interpretation'; citations: string[] }[];
  limitations?: string[];
  insufficient_evidence?: boolean;
  policy_refusal?: boolean;
  disposition?: 'answered' | 'investment_advice' | 'out_of_scope';
  rejection_message?: string;
  estimated_charge_usd?: string | null;
  estimate_status: 'available' | 'unavailable';
  evidence: Evidence[];
  usage: {
    query_embedding_input: number | null;
    answer_generation_input: number | null;
    answer_generation_output: number | null;
    complete_request_total: number | null;
    provider_calls: number;
  };
  run_details: Record<string, unknown>;
  created_at: string;
  finished_at?: string;
};
