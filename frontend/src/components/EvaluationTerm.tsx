import { Box } from '@mui/material';
import { Help } from './Help';

const definitions = {
  rag: 'Retrieval-augmented generation: finding relevant source passages before asking a language model to answer, so the answer can be grounded and cited.',
  keyword:
    'Keyword search looks for the same words or phrases used in the question. It is especially useful for names, figures, and filing terminology.',
  vector:
    'Vector search compares numerical representations of meaning, helping it find relevant passages even when the wording differs from the question.',
  weightedHybrid:
    'Weighted hybrid search blends keyword and vector scores. A measured weight controls how much each signal contributes to the final ranking.',
  rrf: 'Reciprocal-rank fusion (RRF) combines the positions of results from keyword and vector searches instead of combining their raw scores.',
  candidates:
    'Candidate passages are the initial set of potentially relevant filing excerpts considered before the final results are selected.',
  topK: 'Top-k is the maximum number of highest-ranked passages kept for evaluation or passed to the next step.',
  hitRate:
    'Hit Rate is the share of reviewed questions for which at least one expected supporting passage appears in the returned results.',
  mrr: 'Mean reciprocal rank (MRR) measures how early the first relevant passage appears. Rank 1 scores 1, rank 2 scores 0.5, and a miss scores 0.',
  latency:
    'Latency is the elapsed time needed to complete a step. Lower latency means a faster result, not necessarily a more accurate one.',
  prompt:
    'A prompt is the set of instructions and supplied evidence given to a language model to guide its answer.',
  groundTruth:
    'Ground Truth is the human-reviewed filing evidence that search is expected to find for each benchmark question.',
  llmJudge:
    'LLM-as-a-judge uses a language model to apply the same evaluation rubric to every generated answer. It supports, but does not replace, human review.',
  semanticParaphrase:
    'A semantic paraphrase asks about the same idea using different wording from the source filing.',
  chunk:
    'A chunk is a bounded passage of filing text stored and searched as one unit while retaining a link to its source.',
  generationTokens:
    'Generation tokens are the text units processed and produced by the answer model; their count is used to estimate usage and cost.',
} as const;

export type EvaluationTermKey = keyof typeof definitions;

export function EvaluationTerm({
  term,
  children,
}: {
  term: EvaluationTermKey;
  children: React.ReactNode;
}) {
  const label = typeof children === 'string' ? children : term;
  return (
    <Box
      component="span"
      sx={{ display: 'inline-flex', alignItems: 'center', whiteSpace: 'nowrap' }}
    >
      {children}
      <Help term={label}>{definitions[term]}</Help>
    </Box>
  );
}
