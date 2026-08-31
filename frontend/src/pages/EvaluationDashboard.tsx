import RefreshIcon from '@mui/icons-material/Refresh';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Pagination,
  Paper,
  Select,
  Skeleton,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import {
  DataGrid,
  type GridColDef,
  type GridRowSelectionModel,
  type GridSortModel,
} from '@mui/x-data-grid';
import { useEffect, useRef, useState } from 'react';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { errorMessage, getJson } from '../api';
import { AppShell } from '../components/AppShell';
import { Help } from '../components/Help';
import { EvaluationNav } from '../components/EvaluationNav';
import { detailPath, PAGE_SIZE, readEvaluationQuery } from '../evaluation';
import { labels, type Cases, type Config, type Summary } from '../types';
function Metric({ name, value, help }: { name: string; value: string; help: string }) {
  return (
    <Card>
      <CardContent>
        <Typography variant="caption" color="text.secondary">
          {name}
        </Typography>
        <Typography variant="h5" sx={{ fontWeight: 750 }}>
          {value}
        </Typography>
        <Typography variant="caption">{help}</Typography>
      </CardContent>
    </Card>
  );
}
const sortField = (sort: string) =>
  sort === 'hit_rate'
    ? 'hit_rate'
    : sort === 'mrr'
      ? 'mrr'
      : sort === 'latency'
        ? 'median_latency_ms'
        : 'official_rank';
const defaultDirection = (field: string): 'asc' | 'desc' =>
  field === 'official_rank' || field === 'median_latency_ms' ? 'asc' : 'desc';
export function EvaluationDashboard() {
  const [urlParams, setUrlParams] = useSearchParams();
  const [initial] = useState(() => readEvaluationQuery(urlParams));
  const [summary, setSummary] = useState<Summary | null>(null),
    [cases, setCases] = useState<Cases | null>(null),
    [error, setError] = useState(''),
    [refresh, setRefresh] = useState(0);
  const [config, setConfig] = useState(initial.configuration),
    [outcome, setOutcome] = useState(initial.outcome),
    [ticker, setTicker] = useState(initial.company),
    [item, setItem] = useState(initial.item),
    [goal, setGoal] = useState(initial.goal),
    [queryType, setQueryType] = useState(initial.queryType),
    [search, setSearch] = useState(initial.search),
    [page, setPage] = useState(initial.page),
    [sort, setSort] = useState(initial.sort),
    [direction, setDirection] = useState<'asc' | 'desc'>(initial.direction);
  const previousFilters = useRef([outcome, ticker, item, goal, queryType]);
  useEffect(() => {
    setError('');
    setSummary(null);
    getJson<Summary>('/api/retrieval-evaluations/current')
      .then((data) => {
        setSummary(data);
        setConfig((value) => value || data.selected_default_id);
      })
      .catch((error: unknown) => setError(errorMessage(error)));
  }, [refresh]);
  useEffect(() => {
    if (!config) return;
    setCases(null);
    getJson<Cases>(`/api/retrieval-evaluations/current/configurations/${config}/cases`)
      .then(setCases)
      .catch((error: unknown) => setError(errorMessage(error)));
  }, [config, refresh]);
  useEffect(() => {
    const query = new URLSearchParams();
    Object.entries({
      configuration: config,
      outcome,
      company: ticker,
      item,
      goal,
      query_type: queryType,
      q: search,
      page: String(page),
      sort,
      sort_direction: direction,
    }).forEach(([key, value]) => value && query.set(key, value));
    setUrlParams(query, { replace: true });
  }, [config, outcome, ticker, item, goal, queryType, search, page, sort, direction, setUrlParams]);
  useEffect(() => {
    document.title = 'Retrieval evaluation · SEC Filing RAG';
    return () => {
      document.title = 'SEC Filing RAG';
    };
  }, []);
  useEffect(() => {
    const next = [outcome, ticker, item, goal, queryType];
    if (next.some((value, index) => value !== previousFilters.current[index])) setPage(1);
    previousFilters.current = next;
  }, [outcome, ticker, item, goal, queryType]);
  if (error)
    return (
      <AppShell>
        <Alert
          severity="error"
          action={<Button onClick={() => setRefresh((v) => v + 1)}>Retry</Button>}
        >
          <Typography variant="h5">Evaluation unavailable</Typography>
          {error}
        </Alert>
      </AppShell>
    );
  if (!summary)
    return (
      <AppShell>
        <Stack aria-busy="true" spacing={2}>
          <Skeleton variant="rounded" height={180} />
          <Skeleton variant="rounded" height={420} />
        </Stack>
      </AppShell>
    );
  const winner = summary.configurations.find((c) => c.id === summary.selected_default_id)!;
  const activeCases = cases?.cases || [];
  const filtered = activeCases.filter(
    (c) =>
      (!outcome || c.outcome === outcome) &&
      (!ticker || c.ticker === ticker) &&
      (!item || c.items.includes(item)) &&
      (!goal || c.goal === goal) &&
      (!queryType || c.query_type === queryType) &&
      c.question.toLowerCase().includes(search.toLowerCase()),
  );
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pages);
  const visible = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const counts = {
    rank_one: activeCases.filter((c) => c.outcome === 'rank_one').length,
    later_hit: activeCases.filter((c) => c.outcome === 'later_hit').length,
    miss: activeCases.filter((c) => c.outcome === 'miss').length,
  };
  const percent = (n: number) =>
    activeCases.length ? `${((n / activeCases.length) * 100).toFixed(1)}%` : '—';
  const columns: GridColDef<Config>[] = [
    { field: 'official_rank', headerName: 'Rank', width: 80 },
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
      field: 'parameter',
      headerName: 'Parameter',
      width: 110,
      sortable: false,
      valueGetter: (_, row) =>
        row.strategy === 'weighted_hybrid'
          ? `α ${row.alpha}`
          : row.strategy === 'rrf'
            ? `k ${row.rrf_k}`
            : '—',
    },
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
      width: 110,
      valueFormatter: (value) => `${Number(value).toFixed(1)} ms`,
    },
  ];
  const selection: GridRowSelectionModel = {
    type: 'include',
    ids: new Set(config ? [config] : []),
  };
  const sortModel: GridSortModel = [{ field: sortField(sort), sort: direction }];
  const warnings = [...summary.warnings, ...(cases?.warnings || [])];
  return (
    <AppShell>
      <Stack spacing={4}>
        <EvaluationNav />
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          sx={{ justifyContent: 'space-between', gap: 2 }}
        >
          <Box>
            <Typography variant="overline" color="primary">
              Current retrieval evaluation
            </Typography>
            <Typography variant="h1">Which strategy wins?</Typography>
            <Stack direction="row" sx={{ gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
              <Chip color="success" label={String(summary.run.status)} />
              <Typography color="text.secondary">
                {String(summary.run.question_count)} reviewed questions · completed{' '}
                {summary.run.finished_at
                  ? new Date(String(summary.run.finished_at)).toLocaleString()
                  : '—'}
              </Typography>
            </Stack>
          </Box>
          <Button startIcon={<RefreshIcon />} onClick={() => setRefresh((v) => v + 1)}>
            Refresh data
          </Button>
        </Stack>
        {warnings.length > 0 && (
          <Alert severity="warning">
            <Typography sx={{ fontWeight: 700 }}>Coverage or integrity warning</Typography>
            {warnings.map((warning, index) => (
              <Typography key={index}>{warning.message || JSON.stringify(warning)}</Typography>
            ))}
          </Alert>
        )}
        <Paper sx={{ p: 3, bgcolor: 'primary.dark', color: 'primary.contrastText' }}>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', md: '2fr repeat(3,1fr)' },
              gap: 2,
            }}
          >
            <Box>
              <Typography variant="overline">Selected default</Typography>
              <Typography variant="h2">{labels[winner.strategy]} leads this benchmark</Typography>
              <Typography>
                It ranks highest under the evaluator’s official quality, latency, and simplicity
                rules. Inspect the {counts.miss} misses and later-ranked hits below before drawing
                production conclusions.
              </Typography>
            </Box>
            <Metric
              name="Hit Rate"
              value={`${(winner.hit_rate * 100).toFixed(1)}%`}
              help="Relevant evidence found in top-k"
            />
            <Metric name="MRR" value={winner.mrr.toFixed(3)} help="Rewards earlier first matches" />
            <Metric
              name="Median latency"
              value={`${winner.median_latency_ms.toFixed(1)} ms`}
              help="Middle retrieval response time"
            />
          </Box>
        </Paper>
        <section>
          <Typography variant="overline" color="primary">
            How to interpret these results
          </Typography>
          <Typography variant="h2">Quality and speed answer different questions</Typography>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', md: 'repeat(2,1fr)' },
              gap: 2,
              mt: 2,
            }}
          >
            <Typography>
              <b>Hit Rate</b> asks whether expected evidence appears within top-k{' '}
              <Help term="top-k">
                The number of highest-ranked chunks checked for an expected match.
              </Help>
              . It measures coverage, not rank.
            </Typography>
            <Typography>
              <b>MRR</b> rewards putting the first useful result early. Higher values mean reviewers
              typically find evidence sooner.
            </Typography>
            <Typography>
              <b>Latency</b> measures retrieval responsiveness. Fast results are not necessarily
              correct results.
            </Typography>
            <Typography>
              <b>Winner</b> means best only for this reviewed dataset and configuration grid, under
              the official ranking rules{' '}
              <Help term="official ranking rules">
                The evaluator’s ordering of quality, latency, and simplicity tie-breakers.
              </Help>
              .
            </Typography>
          </Box>
          <Stack direction={{ xs: 'column', sm: 'row' }} sx={{ mt: 2, gap: 1 }}>
            {(['rank_one', 'later_hit', 'miss'] as const).map((key) => (
              <Chip
                key={key}
                color={key === 'miss' ? 'error' : key === 'later_hit' ? 'warning' : 'success'}
                label={`${counts[key]} · ${percent(counts[key])} ${labels[key]}`}
              />
            ))}
          </Stack>
        </section>
        <Paper component="details" sx={{ p: 2 }}>
          <Typography component="summary" fontWeight={700}>
            Run and corpus technical details
          </Typography>
          <Box component="pre" sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
            {JSON.stringify({ run: summary.run, lineage: summary.lineage }, null, 2)}
          </Box>
        </Paper>
        <section>
          <Typography variant="overline" color="primary">
            Strategy comparison
          </Typography>
          <Typography variant="h2">Best configuration by approach</Typography>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: 'repeat(2,1fr)', lg: 'repeat(4,1fr)' },
              gap: 1,
              my: 2,
            }}
          >
            {Object.entries(summary.strategy_best).map(([strategy, id]) => {
              const candidate = summary.configurations.find((value) => value.id === id)!;
              return (
                <Card
                  key={strategy}
                  sx={{ borderColor: config === id ? 'primary.main' : 'divider' }}
                >
                  <CardActionArea onClick={() => setConfig(id)}>
                    <CardContent>
                      <Typography variant="caption">{labels[strategy]}</Typography>
                      <Typography fontWeight={700}>
                        {(candidate.hit_rate * 100).toFixed(1)}% hit rate
                      </Typography>
                      <Typography variant="caption">
                        MRR {candidate.mrr.toFixed(3)} · {candidate.median_latency_ms.toFixed(1)} ms
                      </Typography>
                    </CardContent>
                  </CardActionArea>
                </Card>
              );
            })}
          </Box>
          <Typography variant="caption">
            All configurations, ordered by the evaluator’s official selection rules{' '}
            <Help term="official ranking rules">
              Quality is compared first, followed by latency and simplicity tie-breakers.
            </Help>
          </Typography>
          <Box
            sx={{
              height: Math.min(640, 112 + summary.configurations.length * 36),
              minHeight: 220,
              width: '100%',
              mt: 1,
            }}
          >
            <DataGrid
              aria-label="Configuration comparison"
              rows={summary.configurations}
              columns={columns}
              density="compact"
              disableMultipleRowSelection
              rowSelectionModel={selection}
              sortModel={sortModel}
              onRowSelectionModelChange={(model) => {
                const id = [...model.ids][0];
                if (id) setConfig(String(id));
              }}
              onRowClick={(params) => setConfig(String(params.id))}
              onSortModelChange={(model) => {
                if (!model[0]) return;
                const field = model[0].field;
                setSort(
                  field === 'median_latency_ms'
                    ? 'latency'
                    : field === 'official_rank'
                      ? 'official'
                      : field,
                );
                setDirection(model[0].sort || defaultDirection(field));
              }}
              getRowClassName={(params) => (params.id === config ? 'active-configuration' : '')}
              sx={{
                '& .active-configuration': { bgcolor: 'primary.light' },
                '& .MuiDataGrid-row:focus-within': {
                  outline: '2px solid',
                  outlineColor: 'primary.main',
                  outlineOffset: -2,
                },
              }}
            />
          </Box>
        </section>
        <section>
          <Typography variant="overline" color="primary">
            Question evidence
          </Typography>
          <Typography variant="h2">Inspect every outcome</Typography>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: 'repeat(2,1fr)', lg: 'repeat(6,1fr)' },
              gap: 1.5,
              my: 2,
            }}
          >
            <Filter
              label="Outcome"
              value={outcome}
              options={['miss', 'later_hit', 'rank_one']}
              setValue={setOutcome}
            />
            <Filter
              label="Company"
              value={ticker}
              options={cases?.facets.tickers || []}
              setValue={setTicker}
            />
            <Filter
              label="Item"
              value={item}
              options={cases?.facets.items || []}
              setValue={setItem}
            />
            <Filter
              label="Goal"
              value={goal}
              options={cases?.facets.goals || []}
              setValue={setGoal}
            />
            <Filter
              label="Query type"
              value={queryType}
              options={cases?.facets.query_types || []}
              setValue={setQueryType}
            />
            <TextField
              size="small"
              label="Question text"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              placeholder="Search questions"
            />
          </Box>
          <Stack spacing={1}>
            {!cases ? (
              <Typography role="status">Loading questions…</Typography>
            ) : visible.length === 0 ? (
              <Alert
                severity="info"
                action={
                  <Button
                    onClick={() => {
                      setOutcome('');
                      setTicker('');
                      setItem('');
                      setGoal('');
                      setQueryType('');
                      setSearch('');
                    }}
                  >
                    Clear filters
                  </Button>
                }
              >
                <Typography fontWeight={700}>No questions match these filters</Typography>
              </Alert>
            ) : (
              visible.map((value) => (
                <Paper
                  key={value.id}
                  component={RouterLink}
                  to={detailPath(config, value.id, urlParams, currentPage)}
                  sx={{
                    p: 2,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 2,
                    textDecoration: 'none',
                    color: 'text.primary',
                    '&:hover': { borderColor: 'primary.main', bgcolor: 'action.hover' },
                    '&:focus-visible': { outline: '2px solid', outlineColor: 'primary.main' },
                  }}
                >
                  <Chip
                    color={
                      value.outcome === 'miss'
                        ? 'error'
                        : value.outcome === 'later_hit'
                          ? 'warning'
                          : 'success'
                    }
                    label={labels[value.outcome]}
                  />
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography fontWeight={700}>{value.question}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {value.ticker} · Item {value.items.join(', ')} ·{' '}
                      {value.goal.replaceAll('_', ' ')} · {value.query_type.replaceAll('_', ' ')}
                    </Typography>
                  </Box>
                  <Button
                    component="span"
                    endIcon={<ChevronRightIcon />}
                    sx={{ display: { xs: 'none', sm: 'inline-flex' } }}
                  >
                    Review evidence
                  </Button>
                  <ChevronRightIcon sx={{ display: { sm: 'none' } }} />
                </Paper>
              ))
            )}
          </Stack>
          <Stack alignItems="center" mt={2} gap={1}>
            <Pagination count={pages} page={currentPage} onChange={(_, value) => setPage(value)} />
            <Typography variant="caption">
              Page {currentPage} of {pages} · {filtered.length} questions
            </Typography>
          </Stack>
        </section>
        <Alert severity="info">
          <Typography fontWeight={700}>Interpret with care.</Typography>This review has narrow
          coverage and many questions are deliberately literal, so it does not prove broad
          production quality. Repeated or overlapping chunks can make evidence look more diverse
          than it is, and ground truth can be incomplete or imperfect.
        </Alert>
      </Stack>
    </AppShell>
  );
}
function Filter({
  label,
  value,
  options,
  setValue,
}: {
  label: string;
  value: string;
  options: string[];
  setValue: (value: string) => void;
}) {
  return (
    <FormControl size="small">
      <InputLabel>{label}</InputLabel>
      <Select label={label} value={value} onChange={(event) => setValue(event.target.value)}>
        <MenuItem value="">All</MenuItem>
        {options.map((option) => (
          <MenuItem key={option} value={option}>
            {labels[option] || option.replaceAll('_', ' ')}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
