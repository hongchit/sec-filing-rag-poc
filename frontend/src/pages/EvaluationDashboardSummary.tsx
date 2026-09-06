import ArrowForward from '@mui/icons-material/ArrowForward';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Skeleton,
  Stack,
  Typography,
} from '@mui/material';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import { useEffect, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { errorMessage, getJson } from '../api';
import { EvaluationPageLayout } from '../components/EvaluationPageLayout';
import { EvaluationTerm } from '../components/EvaluationTerm';
import { PublicOrAppLayout } from '../components/PublicOrAppLayout';
import { labels, type Config, type Summary } from '../types';

export function EvaluationDashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    document.title = 'Retrieval evaluation · SEC Filing RAG';
    setError('');
    getJson<Summary>('/api/retrieval-evaluations/current')
      .then(setSummary)
      .catch((reason: unknown) => setError(errorMessage(reason)));
    return () => {
      document.title = 'SEC Filing RAG';
    };
  }, [refresh]);
  const columns: GridColDef<Config>[] = [
    { field: 'official_rank', headerName: 'Rank', width: 75 },
    {
      field: 'strategy',
      headerName: 'Strategy',
      minWidth: 160,
      flex: 1,
      valueFormatter: (value) => labels[String(value)] || String(value),
    },
    { field: 'candidate_count', headerName: 'Candidates', width: 115 },
    { field: 'top_k', headerName: 'Top-k', width: 90 },
    {
      field: 'hit_rate',
      headerName: 'Hit Rate',
      width: 110,
      valueFormatter: (value) => `${(Number(value) * 100).toFixed(1)}%`,
    },
    {
      field: 'mrr',
      headerName: 'MRR',
      width: 100,
      valueFormatter: (value) => Number(value).toFixed(3),
    },
    {
      field: 'median_latency_ms',
      headerName: 'Latency',
      width: 115,
      valueFormatter: (value) => `${Number(value).toFixed(1)} ms`,
    },
  ];
  const winner = summary?.configurations.find((value) => value.id === summary.selected_default_id);
  return (
    <PublicOrAppLayout>
      <EvaluationPageLayout>
        {error ? (
          <Alert
            severity="error"
            action={<Button onClick={() => setRefresh((value) => value + 1)}>Retry</Button>}
          >
            {error}
          </Alert>
        ) : !summary ? (
          <Stack spacing={2} aria-busy="true">
            <Skeleton height={100} />
            <Skeleton variant="rounded" height={420} />
          </Stack>
        ) : (
          <Stack spacing={4}>
            <Box>
              <Typography variant="overline" color="primary">
                Retrieval evaluation
              </Typography>
              <Typography variant="h1">Which search strategy finds the right passage?</Typography>
              <Typography color="text.secondary" mt={1}>
                Compare <EvaluationTerm term="keyword">keyword</EvaluationTerm>,{' '}
                <EvaluationTerm term="vector">vector</EvaluationTerm>,{' '}
                <EvaluationTerm term="weightedHybrid">weighted hybrid</EvaluationTerm>, and{' '}
                <EvaluationTerm term="rrf">reciprocal rank fusion (RRF)</EvaluationTerm> on{' '}
                {String(summary.run.question_count)} human-reviewed questions.
              </Typography>
            </Box>
            {winner && (
              <Box display="grid" gridTemplateColumns={{ xs: '1fr', md: 'repeat(3,1fr)' }} gap={2}>
                {[
                  ['Selected strategy', labels[winner.strategy] || winner.strategy],
                  ['Hit Rate', `${(winner.hit_rate * 100).toFixed(1)}%`],
                  ['MRR', winner.mrr.toFixed(3)],
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
            )}
            <Box>
              <Typography variant="h2">Configuration comparison</Typography>
              <Typography color="text.secondary" mb={2}>
                Hit Rate asks whether evidence was found; MRR rewards finding it near the top.
                Latency measures speed, not correctness.
              </Typography>
              <Typography variant="body2" color="text.secondary" mb={1.5}>
                Table terms: <EvaluationTerm term="candidates">Candidates</EvaluationTerm> ·{' '}
                <EvaluationTerm term="topK">Top-k</EvaluationTerm> ·{' '}
                <EvaluationTerm term="hitRate">Hit Rate</EvaluationTerm> ·{' '}
                <EvaluationTerm term="mrr">MRR</EvaluationTerm> ·{' '}
                <EvaluationTerm term="latency">Latency</EvaluationTerm>
              </Typography>
              <Box height={Math.min(640, 112 + summary.configurations.length * 36)} minHeight={260}>
                <DataGrid
                  rows={summary.configurations}
                  columns={columns}
                  density="compact"
                  disableRowSelectionOnClick
                />
              </Box>
            </Box>
            <Alert
              severity="info"
              action={
                <Button
                  component={RouterLink}
                  to="/evaluation/evidence-search/questions"
                  endIcon={<ArrowForward />}
                >
                  Open Retrieval Evaluation Data
                </Button>
              }
            >
              Inspect every reviewed question and its ranked evidence in Retrieval Evaluation Data.
            </Alert>
            {summary.warnings.map((warning, index) => (
              <Chip key={index} color="warning" label={warning.message || 'Evaluation warning'} />
            ))}
          </Stack>
        )}
      </EvaluationPageLayout>
    </PublicOrAppLayout>
  );
}
