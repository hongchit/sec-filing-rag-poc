import ArrowForward from '@mui/icons-material/ArrowForward';
import GitHub from '@mui/icons-material/GitHub';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Link,
  Paper,
  Skeleton,
  Stack,
  Typography,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { errorMessage, getJson } from '../api';
import { EvaluationPipeline } from '../components/EvaluationPipeline';
import { EvaluationPageLayout } from '../components/EvaluationPageLayout';
import { EvaluationTerm } from '../components/EvaluationTerm';
import { Help } from '../components/Help';
import { PublicOrAppLayout } from '../components/PublicOrAppLayout';
import { researchPath } from '../evaluation';
import { labels, type EvaluationOverviewValue } from '../types';

const pct = (value: number) => `${(value * 100).toFixed(1)}%`;
const modelStatus = (matches: boolean | null) =>
  matches === true
    ? 'Used now and evaluated'
    : matches === false
      ? 'Current model differs'
      : 'Used for evaluation only';

const stageDetails: Record<
  string,
  { title: string; happens: string; considerations: string; benefits: string }
> = {
  evidence_search: {
    title: 'Find relevant filing passages',
    happens:
      'The question and filing passages are represented by meaning so semantic matches can complement exact keyword matches.',
    considerations:
      'Semantic-matching quality, retrieval throughput, response time, and cost for every query.',
    benefits:
      'A specialized embedding model is lightweight, fast, and economical, while helping paraphrased questions reach relevant evidence.',
  },
  answer_generation: {
    title: 'Generate an answer from retrieved evidence',
    happens:
      'The selected passages are read together and turned into a grounded answer with verifiable citations.',
    considerations:
      'Reasoning quality, instruction following, citation discipline, response time, and cost.',
    benefits:
      'The selected compact model balances capable reasoning and grounded synthesis with practical speed and cost efficiency.',
  },
  answer_judging: {
    title: 'Measure answer relevance consistently',
    happens:
      'A separate evaluation pass compares each answer with the question and reviewed evidence using one rubric.',
    considerations:
      'Rubric adherence, scoring consistency, repeatability, evaluation time, and cost.',
    benefits:
      'The judge scales repeatable comparisons across every answer and stays outside the live Query path; human review remains the final safeguard.',
  },
};

function OverviewContent() {
  const [value, setValue] = useState<EvaluationOverviewValue | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    document.title = 'Evaluation overview · SEC Filing Research';
    void getJson<EvaluationOverviewValue>('/api/evaluation-overview/current')
      .then(setValue)
      .catch((reason: unknown) => setError(errorMessage(reason)));
    return () => {
      document.title = 'SEC Filing RAG';
    };
  }, []);
  if (error)
    return (
      <Alert severity="warning">
        <Typography variant="h5">Evaluation overview is unavailable</Typography>
        {error}
      </Alert>
    );
  if (!value)
    return (
      <Stack spacing={2} aria-busy="true">
        <Skeleton height={100} />
        <Skeleton variant="rounded" height={320} />
      </Stack>
    );

  const keyword = value.retrieval.baselines.keyword;
  const firstDelta = value.retrieval.rank_buckets.rank_one - keyword.rank_buckets.rank_one;
  const buckets = [
    ['rank_one', '#1', '#287a4b'],
    ['rank_two_three', '#2–3', '#5d8d76'],
    ['rank_four_ten', '#4–10', '#d09a49'],
    ['not_found', 'Not found', '#a12c35'],
  ] as const;

  return (
    <Stack spacing={4}>
      <Box maxWidth={900}>
        <Typography variant="overline" color="primary">
          Evaluation
        </Typography>
        <Typography component="h1" variant="h1">
          Measured before it was trusted.
        </Typography>
        <Typography variant="h6" color="text.secondary" fontWeight={400} mt={2}>
          Every setting used in Query was selected from a benchmark of human-reviewed questions, not
          by assumption.
        </Typography>
        <Typography color="text.secondary" mt={2}>
          The benchmark covers {value.benchmark.question_count} questions across three companies,
          six Form 10-K Items, five query goals, and both exact-keyword and{' '}
          <EvaluationTerm term="semanticParaphrase">semantic-paraphrase</EvaluationTerm> questions.
          It measures evidence retrieval separately from answer generation.
        </Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} gap={2} alignItems={{ sm: 'center' }} mt={3}>
          <Link component={RouterLink} to="/evaluation/evidence-search">
            Explore retrieval evaluation
          </Link>
          <Link component={RouterLink} to="/evaluation/answer-quality">
            Explore RAG evaluation
          </Link>
        </Stack>
      </Box>

      <EvaluationPipeline />

      {value.example && (
        <Paper component="section" sx={{ p: { xs: 2, md: 3 }, bgcolor: '#eef4f1' }}>
          <Typography variant="overline" color="primary">
            Human-reviewed benchmark example
          </Typography>
          <Typography variant="h2">{value.example.question}</Typography>
          <Typography color="text.secondary" mt={1}>
            {value.example.ticker} · Form 10-K · Item {value.example.items.join(', ')} ·{' '}
            {value.example.accession}
          </Typography>
          <Button
            variant="contained"
            size="large"
            component={RouterLink}
            to={researchPath(value.example)}
            endIcon={<ArrowForward />}
            sx={{ mt: 2 }}
          >
            Try this question in Query
          </Button>
        </Paper>
      )}

      <Box display="grid" gridTemplateColumns={{ xs: '1fr', md: 'repeat(4,1fr)' }} gap={2}>
        <ProofCard
          title="Finds the supporting passage"
          value={`${value.retrieval.hit_count} of ${value.retrieval.question_count}`}
          detail={
            <>
              The best <EvaluationTerm term="keyword">keyword-only</EvaluationTerm> configuration
              also found {keyword.hit_count} of {value.retrieval.question_count}; ranking is where
              the measured <EvaluationTerm term="weightedHybrid">hybrid</EvaluationTerm> improved.
            </>
          }
        />
        <ProofCard
          title="Puts useful evidence first"
          value={`${value.retrieval.rank_buckets.rank_one} of ${value.retrieval.question_count}`}
          detail={`${Math.abs(firstDelta)} ${firstDelta === 1 ? 'question' : 'questions'} ${firstDelta >= 0 ? 'more' : 'fewer'} than the best keyword-only configuration tested.`}
        />
        <ProofCard
          title="Produces useful answers"
          value={`${value.generation.relevant_count} of ${value.generation.question_count}`}
          detail="Answers assigned the strongest evaluation verdict for responsiveness, correctness, and support."
        />
        <ProofCard
          title="Keeps citations verifiable"
          value={`${value.generation.valid_citation_handles} of ${value.generation.citation_handles}`}
          detail="Citations that matched evidence supplied to the answer model, with none pointing outside the evaluated Library snapshot."
        />
      </Box>

      <Paper component="section" sx={{ p: { xs: 2, md: 3 } }}>
        <Typography variant="overline" color="primary">
          Where the supporting passage appeared
        </Typography>
        <Typography variant="h2">Most useful evidence arrives first</Typography>
        <Box
          mt={2}
          display="flex"
          height={34}
          borderRadius={2}
          overflow="hidden"
          aria-label={`Rank distribution: ${value.retrieval.rank_buckets.rank_one} at rank one, ${value.retrieval.rank_buckets.rank_two_three} at ranks two to three, ${value.retrieval.rank_buckets.rank_four_ten} at ranks four to ten, ${value.retrieval.rank_buckets.not_found} not found`}
        >
          {buckets.map(([key, label, color]) => {
            const count = value.retrieval.rank_buckets[key];
            return count ? (
              <Box
                key={key}
                bgcolor={color}
                color="white"
                width={`${(count / value.retrieval.question_count) * 100}%`}
                display="grid"
                sx={{ placeItems: 'center', minWidth: count ? 22 : 0 }}
                title={`${label}: ${count}`}
              >
                <Typography variant="caption" fontWeight={750}>
                  {count}
                </Typography>
              </Box>
            ) : null;
          })}
        </Box>
        <Stack direction="row" gap={2} flexWrap="wrap" mt={1.5}>
          {buckets.map(([key, label, color]) => (
            <Stack direction="row" gap={0.75} alignItems="center" key={key}>
              <Box width={10} height={10} borderRadius="50%" bgcolor={color} />
              <Typography variant="caption">
                {label}: {value.retrieval.rank_buckets[key]}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </Paper>

      <section>
        <Typography variant="overline" color="primary">
          Models across the process
        </Typography>
        <Typography variant="h2">Different models handle different stages</Typography>
        <Box display="grid" gridTemplateColumns={{ xs: '1fr', md: 'repeat(3,1fr)' }} gap={2} mt={2}>
          {value.models.map((model, index) => {
            const detail = stageDetails[model.stage] || {
              title: model.role,
              happens: model.role,
              considerations: 'Task quality, reliability, response time, and cost.',
              benefits:
                'The model was evaluated for this defined role before its results were published.',
            };
            return (
              <Card key={model.stage}>
                <CardContent>
                  <Typography variant="overline" color="primary">
                    Step {index + 1}
                  </Typography>
                  <Typography variant="h3">{detail.title}</Typography>
                  <Typography mt={1}>{detail.happens}</Typography>
                  <Typography variant="caption" color="text.secondary" display="block" mt={2}>
                    Selection considerations
                  </Typography>
                  <Typography variant="body2">{detail.considerations}</Typography>
                  <Typography variant="caption" color="text.secondary" display="block" mt={2}>
                    Model used
                  </Typography>
                  <Typography fontWeight={750} sx={{ overflowWrap: 'anywhere' }}>
                    {model.evaluated_model}
                  </Typography>
                  {model.active_model && model.active_model !== model.evaluated_model && (
                    <Typography variant="caption" color="text.secondary" display="block">
                      Active model: {model.active_model}
                    </Typography>
                  )}
                  <Chip
                    sx={{ mt: 1 }}
                    color={model.matches === false ? 'warning' : 'success'}
                    variant={model.matches === null ? 'outlined' : 'filled'}
                    label={modelStatus(model.matches)}
                  />
                  <Typography variant="caption" color="text.secondary" display="block" mt={2}>
                    Strengths and benefits
                  </Typography>
                  <Typography variant="body2">{detail.benefits}</Typography>
                </CardContent>
              </Card>
            );
          })}
        </Box>
        <Typography color="text.secondary" mt={1.5}>
          The benchmark questions and Ground Truth{' '}
          <Help term="Ground Truth">
            The human-reviewed filing passages that retrieval is expected to find for each test
            question.
          </Help>{' '}
          were finalized through human review.
        </Typography>
      </section>

      <Paper component="section" sx={{ p: { xs: 2, md: 3 } }}>
        <Typography variant="overline" color="primary">
          Evaluation process
        </Typography>
        <Typography variant="h2">
          The system was tested and tuned before it was made available to users.
        </Typography>
        <Typography color="text.secondary" mt={1}>
          Retrieval configurations were compared using the same Ground Truth. Prompts then answered
          the same reviewed questions from the same evidence. LLM-as-a-judge{' '}
          <Help term="LLM-as-a-judge">
            An LLM automatically evaluates a generated answer by comparing it with the question and
            human-reviewed reference evidence, then assigns a relevance verdict based on the same
            rubric. No manual grading is performed during the evaluation process.
          </Help>{' '}
          assessed whether each answer was responsive and supported, while separate citation checks
          verified its references. The strongest eligible settings were selected for use in Query.
        </Typography>
      </Paper>

      {value.models.some((model) => model.matches === false) && (
        <Alert severity="warning">
          An active model differs from the evaluated model. The measurements below remain attached
          to the evaluated model and are not presented as evidence for the active replacement.
        </Alert>
      )}

      <Paper component="details" sx={{ p: 2 }}>
        <Typography component="summary" fontWeight={750} sx={{ cursor: 'pointer' }}>
          Models and measurements behind this result
        </Typography>
        <Box display="grid" gridTemplateColumns={{ xs: '1fr', md: 'repeat(2,1fr)' }} gap={2} mt={2}>
          <ExactDetails title="Evidence search">
            Selected approach:{' '}
            {labels[value.retrieval.selected_strategy] || value.retrieval.selected_strategy}
            {' · '}
            <EvaluationTerm term="hitRate">Hit Rate</EvaluationTerm> {pct(value.retrieval.hit_rate)}
            {' · '}
            <EvaluationTerm term="mrr">MRR</EvaluationTerm> {value.retrieval.mrr.toFixed(3)}
            {' · '}median <EvaluationTerm term="latency">latency</EvaluationTerm>{' '}
            {value.retrieval.median_latency_ms.toFixed(1)} ms
          </ExactDetails>
          <ExactDetails title="Answer quality">
            {value.generation.relevant_count} relevant · {value.generation.partly_relevant_count}{' '}
            partly relevant · {value.generation.non_relevant_count} non-relevant ·{' '}
            {value.generation.failures} failures
          </ExactDetails>
          <ExactDetails title="Citation, speed, and cost">
            {value.generation.valid_citation_handles}/{value.generation.citation_handles} valid
            citations ·{' '}
            {value.generation.median_latency_ms == null
              ? 'latency unavailable'
              : `${(value.generation.median_latency_ms / 1000).toFixed(2)} s median generation`}
            {' · '}
            {value.generation.generation_cost_per_answer_usd == null
              ? 'cost unavailable'
              : `$${Number(value.generation.generation_cost_per_answer_usd).toFixed(4)} per answer`}
          </ExactDetails>
          <ExactDetails title="Fair comparison">
            {value.benchmark.question_count} human-reviewed questions · fixed Library snapshot ·
            same retrieved evidence for every prompt · completed{' '}
            {new Date(value.benchmark.finished_at).toLocaleString()}
          </ExactDetails>
        </Box>
        <Stack direction="row" gap={2} flexWrap="wrap" mt={2}>
          <Link component={RouterLink} to="/evaluation/evidence-search">
            Open exact retrieval metrics
          </Link>
          <Link component={RouterLink} to="/evaluation/answer-quality">
            Open exact answer metrics
          </Link>
        </Stack>
      </Paper>

      <Alert severity="info">
        <Typography fontWeight={750}>Limits of this benchmark</Typography>
        It covers the reviewed questions, model versions, prompts, and the displayed filing
        snapshot—not every future question. LLM-as-a-judge offers consistent automated measurement
        instead of human Ground Truth. This research aids verification and should not be considered
        investment advice.
      </Alert>

      <Link
        href="https://github.com/hongchit/sec-filing-rag-poc"
        target="_blank"
        rel="noreferrer"
        display="inline-flex"
        alignItems="center"
        gap={0.75}
      >
        <GitHub fontSize="small" /> View the implementation on GitHub
      </Link>
    </Stack>
  );
}

function ProofCard({
  title,
  value,
  detail,
}: {
  title: string;
  value: string;
  detail: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent>
        <Typography variant="caption" color="text.secondary">
          {title}
        </Typography>
        <Typography variant="h4" fontWeight={800} mt={0.5}>
          {value}
        </Typography>
        <Typography variant="body2" mt={1}>
          {detail}
        </Typography>
      </CardContent>
    </Card>
  );
}

function ExactDetails({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Box>
      <Typography fontWeight={750}>{title}</Typography>
      <Typography color="text.secondary">{children}</Typography>
    </Box>
  );
}

export function EvaluationOverview() {
  return (
    <PublicOrAppLayout>
      <EvaluationPageLayout>
        <OverviewContent />
      </EvaluationPageLayout>
    </PublicOrAppLayout>
  );
}
