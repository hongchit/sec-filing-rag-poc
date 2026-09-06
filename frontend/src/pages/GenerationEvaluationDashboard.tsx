import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Skeleton,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { DataGrid, type GridColDef, type GridEventListener } from '@mui/x-data-grid';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { errorMessage, getJson } from '../api';
import { AppShell } from '../components/AppShell';
import { EvaluationPageLayout } from '../components/EvaluationPageLayout';
import { EvaluationTerm } from '../components/EvaluationTerm';
import { promptNames, verdictColor } from '../generationEvaluation';
import {
  labels,
  type GenerationCases,
  type GenerationMatrixCase,
  type GenerationSummary,
} from '../types';

export function GenerationQuestionResults() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [summary, setSummary] = useState<GenerationSummary | null>(null);
  const [cases, setCases] = useState<GenerationCases | null>(null);
  const [error, setError] = useState('');
  const [promptSource, setPromptSource] = useState<{ prompt_id: string; source: string } | null>(
    null,
  );
  const [promptError, setPromptError] = useState('');
  const search = params.get('q') || '';
  const ticker = params.get('company') || '';
  const item = params.get('item') || '';
  const goal = params.get('goal') || '';
  const queryType = params.get('query_type') || '';
  const attention = params.get('attention') || '';
  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  useEffect(() => {
    Promise.all([
      getJson<GenerationSummary>('/api/generation-evaluations/current'),
      getJson<GenerationCases>('/api/generation-evaluations/current/cases'),
    ])
      .then(([nextSummary, nextCases]) => {
        setSummary(nextSummary);
        setCases(nextCases);
      })
      .catch((reason: unknown) => setError(errorMessage(reason)));
  }, []);

  const filtered = useMemo(
    () =>
      (cases?.cases || []).filter((row) => {
        const verdicts = new Set(row.results.map((result) => result.label));
        const needsAttention = row.results.some(
          (result) => result.label !== 'RELEVANT' || result.failure || !result.citations_valid,
        );
        return (
          (!ticker || row.ticker === ticker) &&
          (!item || row.items.includes(item)) &&
          (!goal || row.goal === goal) &&
          (!queryType || row.query_type === queryType) &&
          (!attention || (attention === 'needs_attention' ? needsAttention : verdicts.size > 1)) &&
          row.question.toLowerCase().includes(search.toLowerCase())
        );
      }),
    [attention, cases, goal, item, queryType, search, ticker],
  );

  if (error)
    return (
      <AppShell>
        <EvaluationPageLayout>
          <Alert severity="error">{error}</Alert>
        </EvaluationPageLayout>
      </AppShell>
    );
  if (!summary || !cases)
    return (
      <AppShell>
        <EvaluationPageLayout>
          <Skeleton variant="rounded" height={520} aria-label="Loading RAG Evaluation Data" />
        </EvaluationPageLayout>
      </AppShell>
    );

  const promptColumns: GridColDef<GenerationMatrixCase>[] = summary.prompts.map((prompt) => ({
    field: prompt.id,
    headerName: promptNames[prompt.id] || prompt.id,
    minWidth: 170,
    flex: 1,
    sortable: false,
    valueGetter: (_, row) =>
      row.results.find((result) => result.prompt_id === prompt.id)?.label || 'FAILED',
    renderCell: (cell) => (
      <Chip
        color={verdictColor(String(cell.value))}
        label={labels[String(cell.value)] || 'Failed'}
      />
    ),
  }));
  const columns: GridColDef<GenerationMatrixCase>[] = [
    { field: 'question', headerName: 'Reviewed question', minWidth: 310, flex: 1.7 },
    ...promptColumns,
  ];
  const clickCell: GridEventListener<'cellClick'> = (cell) => {
    if (!summary.prompts.some((prompt) => prompt.id === cell.field)) return;
    const next = new URLSearchParams(params);
    next.set('prompt', cell.field);
    void navigate(`/evaluation/answer-quality/questions/${cell.id}?${next}`);
  };
  const inspectPrompt = async (id: string) => {
    setPromptError('');
    try {
      setPromptSource(await getJson(`/api/generation-evaluations/current/prompts/${id}`));
    } catch (reason) {
      setPromptError(errorMessage(reason));
    }
  };

  return (
    <AppShell>
      <EvaluationPageLayout>
        <Stack spacing={4}>
          <Box>
            <Typography variant="overline" color="primary">
              RAG Evaluation Data
            </Typography>
            <Typography variant="h1">Answer Comparison</Typography>
            <Typography color="text.secondary" mt={1}>
              Filter reviewed questions, compare each{' '}
              <EvaluationTerm term="prompt">prompt</EvaluationTerm> verdict, and open a cell to
              inspect the complete answers.
            </Typography>
          </Box>
          <Box
            display="grid"
            gridTemplateColumns={{ xs: '1fr', sm: 'repeat(2,1fr)', lg: 'repeat(6,1fr)' }}
            gap={1.5}
          >
            <Filter
              label="Attention"
              value={attention}
              options={[
                ['needs_attention', 'Needs attention'],
                ['disagreement', 'Prompt disagreement'],
              ]}
              onChange={(value) => setFilter('attention', value)}
            />
            <Filter
              label="Company"
              value={ticker}
              options={cases.facets.tickers.map((value) => [value, value])}
              onChange={(value) => setFilter('company', value)}
            />
            <Filter
              label="Item"
              value={item}
              options={cases.facets.items.map((value) => [value, value])}
              onChange={(value) => setFilter('item', value)}
            />
            <Filter
              label="Goal"
              value={goal}
              options={cases.facets.goals.map((value) => [value, value.replaceAll('_', ' ')])}
              onChange={(value) => setFilter('goal', value)}
            />
            <Filter
              label="Query type"
              value={queryType}
              options={cases.facets.query_types.map((value) => [value, value.replaceAll('_', ' ')])}
              onChange={(value) => setFilter('query_type', value)}
            />
            <TextField
              size="small"
              label="Question text"
              value={search}
              onChange={(event) => setFilter('q', event.target.value)}
            />
          </Box>
          <Box height={650}>
            <DataGrid
              aria-label="Question by prompt verdict matrix"
              rows={filtered}
              columns={columns}
              onCellClick={clickCell}
              pageSizeOptions={[10, 25, 50]}
              initialState={{ pagination: { paginationModel: { pageSize: 25, page: 0 } } }}
              sx={{ '& .MuiDataGrid-cell:not([data-field="question"])': { cursor: 'pointer' } }}
            />
          </Box>
          <Paper component="section" variant="outlined" sx={{ p: 2 }}>
            <Typography variant="h2">Prompt source</Typography>
            <Typography color="text.secondary" mb={1}>
              Inspect the protected source used for an evaluated prompt.
            </Typography>
            <Stack direction="row" gap={1} flexWrap="wrap">
              {summary.prompts.map((prompt) => (
                <Button key={prompt.id} size="small" onClick={() => void inspectPrompt(prompt.id)}>
                  {promptNames[prompt.id] || prompt.id}
                </Button>
              ))}
            </Stack>
          </Paper>
        </Stack>
      </EvaluationPageLayout>
      <Dialog
        open={Boolean(promptSource || promptError)}
        onClose={() => {
          setPromptSource(null);
          setPromptError('');
        }}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle>Evaluated prompt source</DialogTitle>
        <DialogContent>
          {promptError ? (
            <Alert severity="warning">{promptError}</Alert>
          ) : (
            <Paper
              component="pre"
              variant="outlined"
              sx={{ p: 2, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}
            >
              {promptSource?.source}
            </Paper>
          )}
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setPromptSource(null);
              setPromptError('');
            }}
          >
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </AppShell>
  );
}

function Filter({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[][];
  onChange: (value: string) => void;
}) {
  return (
    <FormControl size="small">
      <InputLabel>{label}</InputLabel>
      <Select label={label} value={value} onChange={(event) => onChange(event.target.value)}>
        <MenuItem value="">All</MenuItem>
        {options.map(([option, name]) => (
          <MenuItem key={option} value={option}>
            {name}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
