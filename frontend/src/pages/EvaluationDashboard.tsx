import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import {
  Alert,
  Box,
  Button,
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
import { useEffect, useMemo, useState } from 'react';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { errorMessage, getJson } from '../api';
import { AppShell } from '../components/AppShell';
import { EvaluationPageLayout } from '../components/EvaluationPageLayout';
import { EvaluationTerm } from '../components/EvaluationTerm';
import { detailPath, PAGE_SIZE, readEvaluationQuery } from '../evaluation';
import { labels, type Cases, type Summary } from '../types';

export function RetrievalQuestionResults() {
  const [urlParams, setUrlParams] = useSearchParams();
  const [initial] = useState(() => readEvaluationQuery(urlParams));
  const [summary, setSummary] = useState<Summary | null>(null);
  const [cases, setCases] = useState<Cases | null>(null);
  const [error, setError] = useState('');
  const [config, setConfig] = useState(initial.configuration);
  const [outcome, setOutcome] = useState(initial.outcome);
  const [ticker, setTicker] = useState(initial.company);
  const [item, setItem] = useState(initial.item);
  const [goal, setGoal] = useState(initial.goal);
  const [queryType, setQueryType] = useState(initial.queryType);
  const [search, setSearch] = useState(initial.search);
  const [page, setPage] = useState(initial.page);

  useEffect(() => {
    getJson<Summary>('/api/retrieval-evaluations/current')
      .then((data) => {
        setSummary(data);
        setConfig((value) => value || data.selected_default_id);
      })
      .catch((reason: unknown) => setError(errorMessage(reason)));
  }, []);
  useEffect(() => {
    if (!config) return;
    setCases(null);
    getJson<Cases>(`/api/retrieval-evaluations/current/configurations/${config}/cases`)
      .then(setCases)
      .catch((reason: unknown) => setError(errorMessage(reason)));
  }, [config]);
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
    }).forEach(([key, value]) => value && query.set(key, value));
    setUrlParams(query, { replace: true });
  }, [config, outcome, ticker, item, goal, queryType, search, page, setUrlParams]);

  const filtered = useMemo(
    () =>
      (cases?.cases || []).filter(
        (value) =>
          (!outcome || value.outcome === outcome) &&
          (!ticker || value.ticker === ticker) &&
          (!item || value.items.includes(item)) &&
          (!goal || value.goal === goal) &&
          (!queryType || value.query_type === queryType) &&
          value.question.toLowerCase().includes(search.toLowerCase()),
      ),
    [cases, goal, item, outcome, queryType, search, ticker],
  );
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pages);
  const visible = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const updateFilter = (setter: (value: string) => void) => (value: string) => {
    setter(value);
    setPage(1);
  };

  if (error)
    return (
      <AppShell>
        <EvaluationPageLayout>
          <Alert severity="error">{error}</Alert>
        </EvaluationPageLayout>
      </AppShell>
    );
  if (!summary)
    return (
      <AppShell>
        <EvaluationPageLayout>
          <Skeleton variant="rounded" height={420} aria-label="Loading Retrieval Evaluation Data" />
        </EvaluationPageLayout>
      </AppShell>
    );

  return (
    <AppShell>
      <EvaluationPageLayout>
        <Stack spacing={4}>
          <Box>
            <Typography variant="overline" color="primary">
              Retrieval Evaluation Data
            </Typography>
            <Typography variant="h1">Question Evidence</Typography>
            <Typography color="text.secondary" mt={1}>
              Filter reviewed questions and open the ranked filing passages returned by one
              retrieval configuration.
            </Typography>
          </Box>
          <FormControl size="small" sx={{ maxWidth: 420 }}>
            <InputLabel>Retrieval configuration</InputLabel>
            <Select
              label="Retrieval configuration"
              value={config}
              onChange={(event) => {
                setConfig(event.target.value);
                setPage(1);
              }}
            >
              {summary.configurations.map((candidate) => (
                <MenuItem key={candidate.id} value={candidate.id}>
                  {labels[candidate.strategy] || candidate.strategy} · top-{candidate.top_k} ·{' '}
                  {(candidate.hit_rate * 100).toFixed(1)}% hit rate
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Typography variant="body2" color="text.secondary" mt={-3}>
            Each option shows its <EvaluationTerm term="topK">top-k</EvaluationTerm> limit and{' '}
            <EvaluationTerm term="hitRate">Hit Rate</EvaluationTerm> on the reviewed questions.
          </Typography>
          <Box
            display="grid"
            gridTemplateColumns={{ xs: '1fr', sm: 'repeat(2,1fr)', lg: 'repeat(6,1fr)' }}
            gap={1.5}
          >
            <Filter
              label="Outcome"
              value={outcome}
              options={['miss', 'later_hit', 'rank_one']}
              setValue={updateFilter(setOutcome)}
            />
            <Filter
              label="Company"
              value={ticker}
              options={cases?.facets.tickers || []}
              setValue={updateFilter(setTicker)}
            />
            <Filter
              label="Item"
              value={item}
              options={cases?.facets.items || []}
              setValue={updateFilter(setItem)}
            />
            <Filter
              label="Goal"
              value={goal}
              options={cases?.facets.goals || []}
              setValue={updateFilter(setGoal)}
            />
            <Filter
              label="Query type"
              value={queryType}
              options={cases?.facets.query_types || []}
              setValue={updateFilter(setQueryType)}
            />
            <TextField
              size="small"
              label="Question text"
              value={search}
              onChange={(event) => updateFilter(setSearch)(event.target.value)}
            />
          </Box>
          <Stack spacing={1}>
            {!cases ? (
              <Typography role="status">Loading questions…</Typography>
            ) : visible.length === 0 ? (
              <Alert severity="info">No questions match these filters.</Alert>
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
                  <Box flex={1}>
                    <Typography fontWeight={700}>{value.question}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {value.ticker} · Item {value.items.join(', ')} ·{' '}
                      {value.goal.replaceAll('_', ' ')} · {value.query_type.replaceAll('_', ' ')}
                    </Typography>
                  </Box>
                  <Button component="span" endIcon={<ChevronRightIcon />}>
                    Review evidence
                  </Button>
                </Paper>
              ))
            )}
          </Stack>
          <Stack alignItems="center" gap={1}>
            <Pagination count={pages} page={currentPage} onChange={(_, value) => setPage(value)} />
            <Typography variant="caption">
              Page {currentPage} of {pages} · {filtered.length} questions
            </Typography>
          </Stack>
        </Stack>
      </EvaluationPageLayout>
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
