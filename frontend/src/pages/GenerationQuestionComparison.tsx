import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Skeleton,
  Stack,
  Typography,
} from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom';
import { errorMessage, getJson } from '../api';
import { AppShell } from '../components/AppShell';
import { EvidenceReview } from '../components/Evidence';
import { EvaluationTerm } from '../components/EvaluationTerm';
import { researchPath } from '../evaluation';
import {
  labels,
  type EvaluationCase,
  type GenerationCaseResult,
  type GenerationQuestion,
  type GenerationSummary,
} from '../types';
import { promptNames, verdictColor } from '../generationEvaluation';

export function GenerationQuestionComparison() {
  const { questionId = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const [summary, setSummary] = useState<GenerationSummary | null>(null);
  const [detail, setDetail] = useState<GenerationQuestion | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    Promise.all([
      getJson<GenerationSummary>('/api/generation-evaluations/current'),
      getJson<GenerationQuestion>(`/api/generation-evaluations/current/questions/${questionId}`),
    ])
      .then(([nextSummary, nextDetail]) => {
        setSummary(nextSummary);
        setDetail(nextDetail);
      })
      .catch((reason: unknown) => setError(errorMessage(reason)));
  }, [questionId]);
  useEffect(() => {
    document.title = detail
      ? `${detail.question.question} · Generation comparison`
      : 'Generation comparison · SEC Filing RAG';
    return () => {
      document.title = 'SEC Filing RAG';
    };
  }, [detail]);
  const promptIds = summary?.prompts.map((prompt) => prompt.id) || [];
  const first = params.get('prompt') || summary?.selected_prompt_id || promptIds[0] || '';
  const fallback = promptIds.find((id) => id !== first) || first;
  const second =
    params.get('compare') ||
    (summary?.selected_prompt_id !== first ? summary?.selected_prompt_id : fallback) ||
    '';
  const setPrompt = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    next.set(key, value);
    setParams(next, { replace: true });
  };
  const backParams = useMemo(() => {
    const next = new URLSearchParams(params);
    next.delete('prompt');
    next.delete('compare');
    return next;
  }, [params]);
  if (error)
    return (
      <AppShell>
        <Alert severity="error">
          <Typography variant="h5">Answer comparison unavailable</Typography>
          {error}
          <Button component={RouterLink} to="/evaluation/answer-quality/questions">
            Back to RAG Answer Comparison
          </Button>
        </Alert>
      </AppShell>
    );
  if (!summary || !detail)
    return (
      <AppShell>
        <Stack spacing={2} aria-busy="true">
          <Skeleton height={70} />
          <Skeleton variant="rounded" height={500} />
        </Stack>
      </AppShell>
    );
  const result = (id: string) => detail.results.find((item) => item.prompt_id === id);
  const evidenceCase: EvaluationCase = {
    ...detail.question,
    outcome: 'rank_one',
    first_relevant_rank: null,
    expected: detail.expected,
    retrieved: detail.retrieved,
  };
  return (
    <AppShell>
      <Stack spacing={3}>
        <Button
          component={RouterLink}
          to={`/evaluation/answer-quality/questions${backParams.size ? `?${backParams}` : ''}`}
          startIcon={<ArrowBackIcon />}
          sx={{ alignSelf: 'flex-start' }}
        >
          Back to RAG Answer Comparison
        </Button>
        <Paper sx={{ p: { xs: 2, md: 3 } }}>
          <Typography variant="overline" color="primary">
            Reviewed question
          </Typography>
          <Typography component="h1" variant="h2" tabIndex={-1}>
            {detail.question.question}
          </Typography>
          <Typography color="text.secondary">
            {detail.question.ticker} · Item {detail.question.items.join(', ')} ·{' '}
            {detail.question.goal.replaceAll('_', ' ')} ·{' '}
            {detail.question.query_type.replaceAll('_', ' ')}
          </Typography>
          <Button
            variant="contained"
            component={RouterLink}
            to={researchPath(detail.question)}
            sx={{ mt: 2 }}
          >
            Try this question in Query
          </Button>
        </Paper>
        <Box display="grid" gridTemplateColumns={{ xs: '1fr', md: '1fr 1fr' }} gap={2}>
          <ResultColumn
            promptId={first}
            promptIds={promptIds}
            result={result(first)}
            onChange={(value) => setPrompt('prompt', value)}
          />
          <ResultColumn
            promptId={second}
            promptIds={promptIds}
            result={result(second)}
            onChange={(value) => setPrompt('compare', value)}
          />
        </Box>
        <section>
          <Typography variant="overline" color="primary">
            Shared evidence
          </Typography>
          <Typography variant="h2">The evidence supplied to every prompt</Typography>
          <Typography color="text.secondary" sx={{ mb: 2 }}>
            The evaluated prompts used the same retrieved context, so answer differences reflect
            prompt behavior rather than different evidence.
          </Typography>
          {detail.evidence_available ? (
            <EvidenceReview
              item={evidenceCase}
              chunkBaseUrl="/api/generation-evaluations/current/chunks"
            />
          ) : (
            <Alert severity="warning">
              <Typography fontWeight={700}>Evidence is unavailable in this deployment.</Typography>
              The generated answers and recorded citation audits remain visible. Administrator:
              prepare the Library using <code>docs/getting-started.md</code>, then regenerate and
              validate the evaluation using <code>docs/rag-evaluation-workflow.md</code>.
            </Alert>
          )}
        </section>
      </Stack>
    </AppShell>
  );
}

function ResultColumn({
  promptId,
  promptIds,
  result,
  onChange,
}: {
  promptId: string;
  promptIds: string[];
  result?: GenerationCaseResult;
  onChange: (value: string) => void;
}) {
  return (
    <Card component="section">
      <CardContent>
        <FormControl fullWidth size="small" sx={{ mb: 2 }}>
          <InputLabel>Prompt</InputLabel>
          <Select
            label="Prompt"
            value={promptId}
            onChange={(event) => onChange(event.target.value)}
          >
            {promptIds.map((id) => (
              <MenuItem key={id} value={id}>
                {promptNames[id] || id}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        {!result ? (
          <Alert severity="error">This prompt result is unavailable.</Alert>
        ) : (
          <Stack spacing={2}>
            <Stack direction="row" gap={1} flexWrap="wrap">
              <Chip
                color={verdictColor(result.judge?.label || null)}
                label={result.judge ? labels[result.judge.label] : 'Failed'}
              />
              <Chip
                variant="outlined"
                label={result.answer?.disposition.replaceAll('_', ' ') || 'No answer'}
              />
            </Stack>
            {result.failure && <Alert severity="error">{result.failure}</Alert>}
            <Box>
              <Typography variant="h3">Generated answer</Typography>
              {result.answer?.paragraphs.length ? (
                result.answer.paragraphs.map((paragraph, index) => (
                  <Box key={index} sx={{ mt: 1.5 }}>
                    <Chip variant="outlined" label={paragraph.kind.replaceAll('_', ' ')} />
                    <Typography sx={{ mt: 0.5, whiteSpace: 'pre-wrap' }}>
                      {paragraph.text}
                    </Typography>
                    {paragraph.citations.length > 0 && (
                      <Typography variant="caption" color="text.secondary">
                        Citations: {paragraph.citations.join(', ')}
                      </Typography>
                    )}
                  </Box>
                ))
              ) : (
                <Typography color="text.secondary" sx={{ mt: 1 }}>
                  No answer paragraphs were produced.
                </Typography>
              )}
              {result.answer?.limitations.map((limitation) => (
                <Alert severity="info" key={limitation} sx={{ mt: 1 }}>
                  {limitation}
                </Alert>
              ))}
            </Box>
            <Box>
              <Typography variant="h3">
                <EvaluationTerm term="llmJudge">LLM-as-a-judge</EvaluationTerm> assessment
              </Typography>
              <Typography fontWeight={700}>
                {result.judge ? labels[result.judge.label] : 'No verdict'}
              </Typography>
              <Typography>
                {result.judge?.explanation || 'LLM-as-a-judge did not produce an assessment.'}
              </Typography>
            </Box>
            <Box display="grid" gridTemplateColumns="repeat(2,1fr)" gap={1}>
              <SmallMetric
                label="Valid citations"
                value={`${result.citation_audit.valid_citation_handles}/${result.citation_audit.citation_handles}`}
              />
              <SmallMetric
                label="Citations outside the Library"
                value={String(result.citation_audit.cross_corpus_citations)}
              />
              <SmallMetric
                label={<EvaluationTerm term="latency">Latency</EvaluationTerm>}
                value={
                  result.generation_latency_ms == null
                    ? '—'
                    : `${(result.generation_latency_ms / 1000).toFixed(2)} s`
                }
              />
              <SmallMetric
                label={<EvaluationTerm term="generationTokens">Generation tokens</EvaluationTerm>}
                value={result.generation_usage?.total_tokens?.toLocaleString() || '—'}
              />
            </Box>
          </Stack>
        )}
      </CardContent>
    </Card>
  );
}
function SmallMetric({ label, value }: { label: React.ReactNode; value: string }) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography fontWeight={700}>{value}</Typography>
    </Paper>
  );
}
