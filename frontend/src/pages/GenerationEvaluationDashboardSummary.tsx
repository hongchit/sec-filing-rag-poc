import ArrowForward from '@mui/icons-material/ArrowForward';
import { Alert, Box, Button, Card, CardContent, Skeleton, Stack, Typography } from '@mui/material';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import { useMediaQuery } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useEffect, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { errorMessage, getJson } from '../api';
import { EvaluationPageLayout } from '../components/EvaluationPageLayout';
import { EvaluationTerm } from '../components/EvaluationTerm';
import { PublicOrAppLayout } from '../components/PublicOrAppLayout';
import { promptNames } from '../generationEvaluation';
import type { GenerationPromptSummary, GenerationSummary } from '../types';

export function GenerationEvaluationDashboard() {
  const theme = useTheme();
  const compact = useMediaQuery(theme.breakpoints.down('sm'));
  const [summary, setSummary] = useState<GenerationSummary | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    document.title = 'RAG evaluation · SEC Filing RAG';
    getJson<GenerationSummary>('/api/generation-evaluations/current')
      .then(setSummary)
      .catch((reason: unknown) => setError(errorMessage(reason)));
    return () => {
      document.title = 'SEC Filing RAG';
    };
  }, []);
  const columns: GridColDef<GenerationPromptSummary>[] = [
    { field: 'official_rank', headerName: 'Rank', width: 75 },
    {
      field: 'id',
      headerName: 'Prompt',
      minWidth: 210,
      flex: 1,
      valueFormatter: (value) => promptNames[String(value)] || String(value),
    },
    {
      field: 'mean_score',
      headerName: 'Score / 2',
      width: 110,
      valueFormatter: (value) => Number(value).toFixed(3),
    },
    { field: 'relevant_count', headerName: 'Relevant', width: 100 },
    { field: 'valid_citation_handles', headerName: 'Valid citations', width: 125 },
    {
      field: 'median_latency_ms',
      headerName: 'Latency',
      width: 110,
      valueFormatter: (value) => (value == null ? '—' : `${(Number(value) / 1000).toFixed(2)} s`),
    },
  ];
  const winner =
    summary?.prompts.find((value) => value.id === summary.selected_prompt_id) ||
    summary?.prompts[0];
  return (
    <PublicOrAppLayout>
      <EvaluationPageLayout>
        {error ? (
          <Alert severity="error">{error}</Alert>
        ) : !summary || !winner ? (
          <Stack spacing={2} aria-busy="true">
            <Skeleton height={100} />
            <Skeleton variant="rounded" height={420} />
          </Stack>
        ) : (
          <Stack spacing={4}>
            <Box>
              <Typography variant="overline" color="primary">
                RAG evaluation
              </Typography>
              <Typography variant="h1">Which prompt produces the strongest answers?</Typography>
              <Typography color="text.secondary" mt={1}>
                This <EvaluationTerm term="rag">RAG</EvaluationTerm> evaluation compares answer
                relevance, citation validity, speed, and cost on the same reviewed questions and
                evidence.
              </Typography>
            </Box>
            <Box display="grid" gridTemplateColumns={{ xs: '1fr', sm: 'repeat(3,1fr)' }} gap={2}>
              {[
                ['Selected prompt', promptNames[winner.id] || winner.id],
                [
                  'Relevant answers',
                  `${winner.relevant_count} of ${String(summary.run.question_count)}`,
                ],
                [
                  'Valid citations',
                  `${winner.valid_citation_handles} of ${winner.citation_handles}`,
                ],
              ].map(([title, value]) => (
                <Card key={title}>
                  <CardContent>
                    <Typography color="text.secondary" variant="caption">
                      {title}
                    </Typography>
                    <Typography variant="h4" fontWeight={750}>
                      {value}
                    </Typography>
                  </CardContent>
                </Card>
              ))}
            </Box>
            <Box>
              <Typography variant="h2">Prompt comparison</Typography>
              <Typography color="text.secondary" mb={2}>
                <EvaluationTerm term="llmJudge">LLM-as-a-judge</EvaluationTerm> applies one rubric
                consistently; it supplements rather than replaces human review.
              </Typography>
              <Typography variant="body2" color="text.secondary" mb={1.5}>
                Table terms: <EvaluationTerm term="prompt">Prompt</EvaluationTerm> ·{' '}
                <EvaluationTerm term="latency">Latency</EvaluationTerm>
              </Typography>
              {compact ? (
                <Stack spacing={1.5} aria-label="Prompt comparison">
                  {summary.prompts.map((prompt) => (
                    <Card key={prompt.id} variant="outlined">
                      <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                        <Stack spacing={1}>
                          <Stack direction="row" justifyContent="space-between" gap={1}>
                            <Typography fontWeight={750}>
                              {promptNames[prompt.id] || prompt.id}
                            </Typography>
                            <Typography variant="body2">Rank {prompt.official_rank}</Typography>
                          </Stack>
                          <Typography variant="body2">
                            Score {Number(prompt.mean_score).toFixed(3)} / 2 ·{' '}
                            {prompt.relevant_count} relevant
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            {prompt.valid_citation_handles} valid citations ·{' '}
                            {prompt.median_latency_ms == null
                              ? 'latency unavailable'
                              : `${(Number(prompt.median_latency_ms) / 1000).toFixed(2)} s`}
                          </Typography>
                        </Stack>
                      </CardContent>
                    </Card>
                  ))}
                </Stack>
              ) : (
                <Box height={Math.max(300, 112 + summary.prompts.length * 48)} minWidth={0}>
                  <DataGrid
                    rows={summary.prompts}
                    columns={columns}
                    disableRowSelectionOnClick
                    hideFooter
                  />
                </Box>
              )}
            </Box>
            <Alert
              severity="info"
              sx={{
                flexDirection: { xs: 'column', sm: 'row' },
                '& .MuiAlert-action': { ml: { xs: 0, sm: 'auto' }, mt: { xs: 1, sm: 0 } },
              }}
              action={
                <Button
                  component={RouterLink}
                  to="/evaluation/answer-quality/questions"
                  endIcon={<ArrowForward />}
                >
                  Open RAG Evaluation Data
                </Button>
              }
            >
              Inspect question-by-prompt verdicts and complete answers in RAG Evaluation Data.
            </Alert>
          </Stack>
        )}
      </EvaluationPageLayout>
    </PublicOrAppLayout>
  );
}
