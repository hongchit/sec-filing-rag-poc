import RefreshIcon from '@mui/icons-material/Refresh';
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
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
import { EvaluationNav } from '../components/EvaluationNav';
import { Help } from '../components/Help';
import {
  labels,
  type GenerationCases,
  type GenerationMatrixCase,
  type GenerationPromptSummary,
  type GenerationSummary,
} from '../types';
import { promptNames, verdictColor } from '../generationEvaluation';
const money = (value: string | null) => (value == null ? '—' : `$${Number(value).toFixed(4)}`);

function Metric({
  title,
  value,
  help,
  term,
}: {
  title: string;
  value: string;
  help: string;
  term: string;
}) {
  return (
    <Card>
      <CardContent>
        <Typography variant="caption" color="text.secondary">
          {title} <Help term={term}>{help}</Help>
        </Typography>
        <Typography variant="h5" fontWeight={750}>
          {value}
        </Typography>
      </CardContent>
    </Card>
  );
}

export function GenerationEvaluationDashboard() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [summary, setSummary] = useState<GenerationSummary | null>(null);
  const [cases, setCases] = useState<GenerationCases | null>(null);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
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
    setError('');
    Promise.all([
      getJson<GenerationSummary>('/api/generation-evaluations/current'),
      getJson<GenerationCases>('/api/generation-evaluations/current/cases'),
    ])
      .then(([nextSummary, nextCases]) => {
        setSummary(nextSummary);
        setCases(nextCases);
      })
      .catch((reason: unknown) => setError(errorMessage(reason)));
  }, [refresh]);
  useEffect(() => {
    document.title = 'RAG generation evaluation · SEC Filing RAG';
    return () => {
      document.title = 'SEC Filing RAG';
    };
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
        <Alert
          severity="error"
          action={<Button onClick={() => setRefresh((v) => v + 1)}>Retry</Button>}
        >
          <Typography variant="h5">Generation evaluation unavailable</Typography>
          {error}
        </Alert>
      </AppShell>
    );
  if (!summary || !cases)
    return (
      <AppShell>
        <Stack spacing={2} aria-busy="true">
          <Skeleton height={70} />
          <Skeleton variant="rounded" height={200} />
          <Skeleton variant="rounded" height={500} />
        </Stack>
      </AppShell>
    );
  const winner =
    summary.prompts.find((prompt) => prompt.id === summary.selected_prompt_id) ||
    summary.prompts[0];
  const relevantRate = winner ? winner.relevant_count / Number(summary.run.question_count || 1) : 0;
  const citationRate = winner?.citation_handles
    ? winner.valid_citation_handles / winner.citation_handles
    : 0;
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
  const matrixColumns: GridColDef<GenerationMatrixCase>[] = [
    { field: 'question', headerName: 'Reviewed question', minWidth: 310, flex: 1.7 },
    ...promptColumns,
  ];
  const openPrompt = async (id: string) => {
    setPromptError('');
    try {
      setPromptSource(await getJson(`/api/generation-evaluations/current/prompts/${id}`));
    } catch (reason) {
      setPromptError(errorMessage(reason));
    }
  };
  const clickCell: GridEventListener<'cellClick'> = (cell) => {
    if (!summary.prompts.some((prompt) => prompt.id === cell.field)) return;
    const next = new URLSearchParams(params);
    next.set('prompt', cell.field);
    void navigate(`/evaluation/generation/questions/${cell.id}?${next}`);
  };
  const recoveryDocs = [
    ...new Set(summary.warnings.flatMap((warning) => warning.recovery_docs || [])),
  ];
  return (
    <AppShell>
      <Stack spacing={4}>
        <EvaluationNav />
        <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={2}>
          <Box>
            <Typography variant="overline" color="primary">
              Current RAG generation evaluation
            </Typography>
            <Typography variant="h1">Which prompt produces the strongest answers?</Typography>
            <Typography color="text.secondary">
              {String(summary.run.question_count)} reviewed questions ·{' '}
              {String(summary.run.prompt_count)} prompts · completed{' '}
              {new Date(String(summary.run.finished_at)).toLocaleString()}
            </Typography>
          </Box>
          <Button startIcon={<RefreshIcon />} onClick={() => setRefresh((value) => value + 1)}>
            Refresh data
          </Button>
        </Stack>
        {summary.warnings.length > 0 && (
          <Alert severity="warning">
            <Typography fontWeight={700}>Deployment data is incomplete</Typography>
            {summary.warnings.map((warning) => (
              <Typography key={warning.code}>{warning.message}</Typography>
            ))}
            <Typography sx={{ mt: 1 }}>
              Administrator: prepare the corpus using <code>docs/getting-started.md</code>, then
              regenerate and validate the evaluation using{' '}
              <code>docs/rag-evaluation-workflow.md</code>.
            </Typography>
            {recoveryDocs.length > 0 && (
              <Typography variant="caption">
                Recovery documentation: {recoveryDocs.join(' · ')}
              </Typography>
            )}
          </Alert>
        )}
        <Paper sx={{ p: 3, bgcolor: 'primary.dark', color: 'primary.contrastText' }}>
          <Box display="grid" gridTemplateColumns={{ xs: '1fr', md: '2fr repeat(4,1fr)' }} gap={2}>
            <Box>
              <Typography variant="overline">Selected prompt</Typography>
              <Typography variant="h2">
                {promptNames[winner.id] || winner.id} leads this run
              </Typography>
              <Typography>
                {summary.selected_prompt_id === summary.promoted_prompt_id
                  ? 'It is also the prompt currently promoted for runtime research.'
                  : 'The evaluated winner is not the currently promoted runtime prompt; human review is still required.'}
              </Typography>
            </Box>
            <Metric
              title="Relevant answers"
              value={`${(relevantRate * 100).toFixed(1)}%`}
              term="relevant answers"
              help="Share assigned the strongest judge verdict for responsiveness, correctness, and support."
            />
            <Metric
              title="Citation validity"
              value={winner.citation_handles ? `${(citationRate * 100).toFixed(1)}%` : '—'}
              term="citation validity"
              help="Citations that exactly match evidence handles supplied to the answer generator."
            />
            <Metric
              title="Median latency"
              value={
                winner.median_latency_ms == null
                  ? '—'
                  : `${(winner.median_latency_ms / 1000).toFixed(2)} s`
              }
              term="median latency"
              help="Middle answer-generation time; it excludes judge time."
            />
            <Metric
              title="Answer cost"
              value={money(winner.generation_cost_per_answer_usd)}
              term="answer cost"
              help="Estimated generation cost per answer using the run's stored pricing snapshot; judge cost is excluded."
            />
          </Box>
        </Paper>
        <section>
          <Typography variant="overline" color="primary">
            How to interpret these results
          </Typography>
          <Typography variant="h2">
            Quality, controls, speed, and cost inform one decision
          </Typography>
          <Box
            display="grid"
            gridTemplateColumns={{ xs: '1fr', md: 'repeat(2,1fr)' }}
            gap={2}
            mt={2}
          >
            <Typography>
              <b>Relevance</b> is an LLM judge verdict, not human ground truth. Inspect
              disagreements and explanations before promotion.
            </Typography>
            <Typography>
              <b>Eligibility</b> requires complete judging, no failures, valid citation handles, and
              no cross-corpus citations.
            </Typography>
            <Typography>
              <b>Fair comparison</b> means every prompt received the same reviewed questions,
              retrieved context, generation model, and judge.
            </Typography>
            <Typography>
              <b>Winner</b> applies only to this run. The evaluator orders eligible prompts by
              score, relevant count, latency, then prompt ID.
            </Typography>
          </Box>
        </section>
        <section>
          <Typography variant="overline" color="primary">
            Prompt leaderboard
          </Typography>
          <Typography variant="h2">Compare the candidate behaviors</Typography>
          <Box height={Math.max(260, 115 + summary.prompts.length * 48)} mt={2}>
            <DataGrid
              rows={summary.prompts}
              columns={
                [
                  { field: 'official_rank', headerName: 'Rank', width: 75 },
                  {
                    field: 'id',
                    headerName: 'Prompt',
                    minWidth: 210,
                    flex: 1,
                    valueFormatter: (value) => promptNames[String(value)] || value,
                  },
                  {
                    field: 'mean_score',
                    headerName: 'Score / 2',
                    width: 105,
                    valueFormatter: (value) => Number(value).toFixed(3),
                  },
                  { field: 'relevant_count', headerName: 'Relevant', width: 100 },
                  { field: 'partly_relevant_count', headerName: 'Partial', width: 90 },
                  {
                    field: 'eligible',
                    headerName: 'Eligible',
                    width: 100,
                    renderCell: (cell) => (
                      <Chip
                        color={cell.value ? 'success' : 'error'}
                        label={cell.value ? 'Yes' : 'No'}
                      />
                    ),
                  },
                  {
                    field: 'median_latency_ms',
                    headerName: 'Latency',
                    width: 105,
                    valueFormatter: (value) =>
                      value == null ? '—' : `${(Number(value) / 1000).toFixed(2)} s`,
                  },
                  {
                    field: 'generation_cost_per_answer_usd',
                    headerName: 'Answer cost',
                    width: 115,
                    valueFormatter: money,
                  },
                  {
                    field: 'details',
                    headerName: '',
                    width: 120,
                    sortable: false,
                    renderCell: (cell) => (
                      <Button
                        size="small"
                        startIcon={<VisibilityOutlinedIcon />}
                        onClick={() => void openPrompt(cell.row.id)}
                      >
                        View prompt
                      </Button>
                    ),
                  },
                ] as GridColDef<GenerationPromptSummary>[]
              }
              disableRowSelectionOnClick
              hideFooter
            />
          </Box>
        </section>
        <section>
          <Typography variant="overline" color="primary">
            Question-by-prompt comparison
          </Typography>
          <Typography variant="h2">Find disagreements and inspect answers</Typography>
          <Box
            display="grid"
            gridTemplateColumns={{ xs: '1fr', sm: 'repeat(2,1fr)', lg: 'repeat(6,1fr)' }}
            gap={1.5}
            my={2}
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
              aria-label="Question by prompt result matrix"
              rows={filtered}
              columns={matrixColumns}
              onCellClick={clickCell}
              pageSizeOptions={[10, 25, 50]}
              initialState={{ pagination: { paginationModel: { pageSize: 25, page: 0 } } }}
              sx={{ '& .MuiDataGrid-cell:not([data-field="question"])': { cursor: 'pointer' } }}
            />
          </Box>
        </section>
        <Alert severity="info">
          <Typography fontWeight={700}>Interpret with care.</Typography>The judge is a consistent
          measurement instrument, not a substitute for human calibration. Small differences may
          reflect judge preference or provider variation.
        </Alert>
      </Stack>
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
            <>
              <Typography color="text.secondary" gutterBottom>
                {promptSource && (promptNames[promptSource.prompt_id] || promptSource.prompt_id)}
              </Typography>
              <Paper
                component="pre"
                variant="outlined"
                sx={{ p: 2, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}
              >
                {promptSource?.source}
              </Paper>
            </>
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
        {options.map(([key, text]) => (
          <MenuItem key={key} value={key}>
            {text}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
