import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Collapse,
  FormControl,
  InputLabel,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { useAccount } from '../account';
import { goalEntries, goals, type ResearchGoal } from '../goals';
import { streamResearch, recoverResearch } from '../researchApi';
import type { Company, CompanyStatus, Evidence, Research as ResearchValue } from '../researchTypes';
import { preparationSubmissionMessage } from '../preparationErrors';

const items = ['1', '1A', '3', '7', '7A', '8'];
export function Research() {
  const location = useLocation();
  const prefill = useRef(() => {
    const params = new URLSearchParams(location.search);
    const requestedGoal = params.get('goal');
    const validGoal =
      requestedGoal && requestedGoal in goals ? (requestedGoal as ResearchGoal) : null;
    const requestedItems = (params.get('items') || '')
      .split(',')
      .filter((value) => items.includes(value));
    return {
      ticker: (params.get('company') || '').toUpperCase(),
      goal: validGoal,
      question: (params.get('question') || '').slice(0, 2000),
      items: requestedItems,
      accession: (params.get('accession') || '').slice(0, 32),
    };
  }).current();
  const retry = useRef(
    (location.state as { retry?: ResearchValue; advanced?: boolean } | null) ?? null,
  ).current;
  const account = useAccount();
  const remaining = Number(account?.budget.remaining_usd ?? 0);
  const canResearch = remaining >= Number(account?.action_reservations.research_usd ?? Infinity);
  const canPrepare =
    remaining >= Number(account?.action_reservations.corpus_preparation_usd ?? Infinity);
  const navigate = useNavigate();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [statuses, setStatuses] = useState<Record<string, CompanyStatus>>({});
  const [ticker, setTicker] = useState('');
  const [corpus, setCorpus] = useState('');
  const [goal, setGoal] = useState<ResearchGoal>(retry?.retry?.goal ?? prefill.goal ?? 'business');
  const [question, setQuestion] = useState(retry?.retry?.question ?? prefill.question);
  const [allowed, setAllowed] = useState<string[]>(retry?.retry?.allowed_items ?? prefill.items);
  const [advanced, setAdvanced] = useState(
    retry?.advanced ?? (Array.isArray(retry?.retry?.allowed_items) || prefill.items.length > 0),
  );
  const [stage, setStage] = useState('');
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [error, setError] = useState('');
  const [prefillNotice, setPrefillNotice] = useState('');
  const [recent, setRecent] = useState<ResearchValue[]>([]);
  const [prepareOpen, setPrepareOpen] = useState(false);
  const [prepareYear, setPrepareYear] = useState(String(new Date().getUTCFullYear() - 1));
  const [preparation, setPreparation] = useState('');
  const [latestPreparation, setLatestPreparation] = useState('');
  const refreshCompanies = useCallback(async () => {
    const response = await fetch('/api/companies');
    if (!response.ok) throw new Error('Company status is unavailable.');
    const values = (await response.json()) as Company[];
    setCompanies(values);
    const ready: Record<string, CompanyStatus> = {};
    for (const company of values.filter((value) => value.enabled)) {
      const statusResponse = await fetch(`/api/companies/${company.ticker}/status`);
      if (statusResponse.ok) ready[company.ticker] = (await statusResponse.json()) as CompanyStatus;
    }
    setStatuses(ready);
    const firstReady = values.find((value) => value.enabled && ready[value.ticker]?.active_corpus);
    const firstEnabled = values.find((value) => value.enabled);
    if (retry?.retry) {
      setTicker(retry.retry.ticker);
      setCorpus(retry.retry.corpus_version_id);
    } else {
      setTicker((current) => {
        const requested = values.find(
          (value) => value.enabled && value.ticker === prefill.ticker && ready[value.ticker],
        );
        const selected =
          requested?.ticker ??
          (current && ready[current]?.active_corpus ? current : undefined) ??
          firstReady?.ticker ??
          (current || firstEnabled?.ticker || '');
        const status = ready[selected];
        const filing = prefill.accession
          ? [status?.active_corpus, ...(status?.historical_corpora || [])].find(
              (value) => value?.accession === prefill.accession,
            )
          : null;
        setCorpus(filing?.corpus_version_id ?? status?.active_corpus?.corpus_version_id ?? '');
        setPrefillNotice(
          !prefill.accession || filing
            ? ''
            : requested && status?.active_corpus
              ? 'The filing used in the evaluation is not available here. The latest available filing has been selected instead.'
              : requested
                ? 'The filing used in the evaluation is not currently available in Query.'
                : 'The company and filing used in the evaluation are not available here. Another available company has been selected instead.',
        );
        return selected;
      });
    }
  }, [prefill.accession, prefill.ticker, retry]);
  const pollLatestBatch = useCallback(
    async function poll(batchId: string, started = Date.now()) {
      if (Date.now() - started >= 10 * 60_000) {
        setLatestPreparation(
          'Preparation is still running. Select Check latest batch to resume polling.',
        );
        return;
      }
      const response = await fetch(`/api/filing-batches/${batchId}`);
      if (response.ok) {
        const batch = (await response.json()) as {
          status: string;
          items: { status: string; safe_error?: string }[];
        };
        if (['succeeded', 'partial_failure', 'failed'].includes(batch.status)) {
          localStorage.removeItem('research-preparation:latest');
          await refreshCompanies();
          if (batch.status === 'succeeded') setLatestPreparation('Latest filings ready.');
          else
            setLatestPreparation(
              batch.items.find((item) => item.safe_error)?.safe_error ??
                'Some latest filings could not be prepared. Ready Library filings remain available.',
            );
          return;
        }
      }
      setLatestPreparation(
        'Preparing latest filings… Server-side work continues if this tab closes.',
      );
      const delay = Date.now() - started < 30_000 ? 2_000 : 5_000;
      window.setTimeout(() => void poll(batchId, started), delay);
    },
    [refreshCompanies],
  );
  const pollBatch = useCallback(async function poll(
    batchId: string,
    selectedTicker: string,
    year: string,
    started = Date.now(),
  ) {
    if (Date.now() - started >= 10 * 60_000) {
      setPreparation('Preparation is still running. Select Check again to resume polling.');
      return;
    }
    const response = await fetch(`/api/filing-batches/${batchId}`);
    if (response.ok) {
      const batch = (await response.json()) as {
        status: string;
        items: { status: string; safe_error?: string }[];
      };
      if (batch.status === 'succeeded') {
        localStorage.removeItem(`research-preparation:${selectedTicker}:${year}`);
        const refreshed = await fetch(`/api/companies/${selectedTicker}/status`);
        if (refreshed.ok) {
          const next = (await refreshed.json()) as CompanyStatus;
          setStatuses((old) => ({ ...old, [selectedTicker]: next }));
          const exact = [next.active_corpus, ...next.historical_corpora].find((item) =>
            item?.report_date.startsWith(year),
          );
          if (exact) setCorpus(exact.corpus_version_id);
        }
        setPreparation('Filing ready.');
        return;
      }
      if (
        ['failed', 'partial_failure'].includes(batch.status) ||
        batch.items.some((item) => ['failed', 'skipped'].includes(item.status))
      ) {
        localStorage.removeItem(`research-preparation:${selectedTicker}:${year}`);
        setPreparation(
          batch.items.find((item) => item.safe_error)?.safe_error ??
            'That filing could not be prepared. Stored ready years remain available.',
        );
        return;
      }
    }
    setPreparation('Preparing filing… Server-side work continues if this tab closes.');
    const delay = Date.now() - started < 30_000 ? 2_000 : 5_000;
    window.setTimeout(() => {
      void poll(batchId, selectedTicker, year, started);
    }, delay);
  }, []);
  async function prepare() {
    const year = Number(prepareYear);
    if (!ticker || year < 1900 || year > 9999) return;
    setPreparation('Submitting preparation…');
    const response = await fetch(`/api/companies/${ticker}/filing-preparations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fiscal_year: year }),
    });
    if (!response.ok) {
      setPreparation(await preparationSubmissionMessage(response));
      return;
    }
    const body = (await response.json()) as { batch_id: string };
    localStorage.setItem(`research-preparation:${ticker}:${prepareYear}`, body.batch_id);
    void pollBatch(body.batch_id, ticker, prepareYear);
  }
  async function prepareLatest() {
    setLatestPreparation('Submitting latest filing preparation…');
    const response = await fetch('/api/filing-batches', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    if (!response.ok) {
      setLatestPreparation(await preparationSubmissionMessage(response));
      return;
    }
    const body = (await response.json()) as { batch_id: string };
    localStorage.setItem('research-preparation:latest', body.batch_id);
    void pollLatestBatch(body.batch_id);
  }
  useEffect(() => {
    void refreshCompanies()
      .then(() => {
        for (let index = 0; index < localStorage.length; index += 1) {
          const storageKey = localStorage.key(index);
          if (storageKey === 'research-preparation:latest') {
            const batchId = localStorage.getItem(storageKey);
            if (batchId) void pollLatestBatch(batchId);
            continue;
          }
          if (!storageKey?.startsWith('research-preparation:')) continue;
          const [, storedTicker, storedYear] = storageKey.split(':');
          const batchId = localStorage.getItem(storageKey);
          if (batchId && storedTicker && storedYear)
            void pollBatch(batchId, storedTicker, storedYear);
        }
      })
      .catch(() => setError('Company status is unavailable.'));
    void fetch('/api/research/history?limit=10')
      .then(async (r) => (r.ok ? ((await r.json()) as { items: ResearchValue[] }) : { items: [] }))
      .then((value) => setRecent(value.items))
      .catch(() => setRecent([]));
  }, [pollBatch, pollLatestBatch, refreshCompanies]);
  const corpora = useMemo(() => {
    const status = statuses[ticker];
    return status
      ? ([status.active_corpus, ...status.historical_corpora].filter(Boolean) as NonNullable<
          CompanyStatus['active_corpus']
        >[])
      : [];
  }, [statuses, ticker]);
  const hasActiveCorpus = Object.values(statuses).some((status) => status.active_corpus);
  async function submit() {
    if (!question.trim() || !ticker || !corpus) return;
    setError('');
    setEvidence([]);
    setStage('retrieving');
    const key = crypto.randomUUID();
    const body = {
      ticker,
      corpus_version_id: corpus,
      goal,
      question,
      allowed_items: allowed.length ? allowed : null,
    };
    try {
      const result = await streamResearch(body, key, (name, data) => {
        setStage(name);
        if (name === 'retrieved') setEvidence((data as { evidence: Evidence[] }).evidence);
      });
      void navigate(`/research/${result.research_id}`);
    } catch (streamError) {
      const id = (streamError as { detail?: { research_id?: string } }).detail?.research_id;
      try {
        const result = await recoverResearch(body, key, id);
        void navigate(`/research/${result.research_id}`);
      } catch {
        setError(
          'The query could not be completed. You can safely retry; the same request will not create duplicate provider work.',
        );
        setStage('');
      }
    }
  }
  return (
    <AppShell>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h1">Query annual filings</Typography>
          <Typography color="text.secondary">
            Ask grounded questions of stored SEC filings.
          </Typography>
        </Box>
        {error && <Alert severity="error">{error}</Alert>}
        {prefillNotice && <Alert severity="info">{prefillNotice}</Alert>}
        {companies.length > 0 && !hasActiveCorpus && (
          <Alert severity="info">
            <Stack spacing={1} alignItems="flex-start">
              <Typography>No searchable filing is ready in the Library yet.</Typography>
              <Button
                variant="contained"
                disabled={
                  !canPrepare ||
                  latestPreparation.startsWith('Submitting') ||
                  latestPreparation.startsWith('Preparing')
                }
                onClick={() => void prepareLatest()}
              >
                Prepare latest filings
              </Button>
              {latestPreparation.includes('still running') && (
                <Button
                  onClick={() => {
                    const batchId = localStorage.getItem('research-preparation:latest');
                    if (batchId) void pollLatestBatch(batchId);
                  }}
                >
                  Check latest batch
                </Button>
              )}
              {latestPreparation && <Typography>{latestPreparation}</Typography>}
              {!canPrepare && (
                <Typography>
                  Your remaining lifetime allowance is below the preparation reservation.
                </Typography>
              )}
            </Stack>
          </Alert>
        )}
        {hasActiveCorpus && latestPreparation && (
          <Alert severity={latestPreparation === 'Latest filings ready.' ? 'success' : 'warning'}>
            {latestPreparation}
          </Alert>
        )}
        <Paper sx={{ p: { xs: 2, md: 4 } }}>
          <Stack spacing={3}>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <FormControl fullWidth>
                <InputLabel>Company</InputLabel>
                <Select
                  label="Company"
                  value={ticker}
                  onChange={(event) => {
                    const next = event.target.value;
                    setTicker(next);
                    setCorpus(statuses[next]?.active_corpus?.corpus_version_id ?? '');
                  }}
                >
                  {companies
                    .filter((c) => c.enabled)
                    .map((c) => (
                      <MenuItem key={c.ticker} value={c.ticker}>
                        {c.ticker}
                        {c.name ? ` — ${c.name}` : ''}
                      </MenuItem>
                    ))}
                </Select>
              </FormControl>
              <FormControl fullWidth>
                <InputLabel>Filing period</InputLabel>
                <Select
                  label="Filing period"
                  value={corpus}
                  onChange={(event) => setCorpus(event.target.value)}
                >
                  {corpora.map((c) => (
                    <MenuItem key={c.corpus_version_id} value={c.corpus_version_id}>
                      {c.report_date.slice(0, 4)} · {c.accession}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl fullWidth>
                <InputLabel>Query goal</InputLabel>
                <Select
                  label="Query goal"
                  value={goal}
                  onChange={(event) => setGoal(event.target.value)}
                >
                  {goalEntries.map(([id, value]) => (
                    <MenuItem key={id} value={id}>
                      {value.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Stack>
            <Button onClick={() => setPrepareOpen((value) => !value)} aria-expanded={prepareOpen}>
              Prepare a filing for another year
            </Button>
            <Collapse in={prepareOpen}>
              <Stack spacing={1}>
                <Alert severity="warning">
                  Preparation can take several minutes, accesses SEC EDGAR, and incurs embedding
                  cost. It begins only after you select Prepare filing.
                </Alert>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                  <TextField
                    label="Exact fiscal year"
                    type="number"
                    value={prepareYear}
                    onChange={(event) => setPrepareYear(event.target.value)}
                  />
                  <Button variant="outlined" disabled={!canPrepare} onClick={() => void prepare()}>
                    Prepare filing
                  </Button>
                  {preparation.includes('still running') && (
                    <Button
                      onClick={() => {
                        const batch = localStorage.getItem(
                          `research-preparation:${ticker}:${prepareYear}`,
                        );
                        if (batch) void pollBatch(batch, ticker, prepareYear);
                      }}
                    >
                      Check again
                    </Button>
                  )}
                </Stack>
                {!canPrepare && (
                  <Alert severity="warning">
                    Your remaining lifetime allowance is below the amount required to prepare a
                    filing. Existing Library filings remain available.
                  </Alert>
                )}
                {preparation && (
                  <Alert
                    severity={preparation.includes('could not') ? 'error' : 'info'}
                    aria-live="polite"
                  >
                    {preparation}
                  </Alert>
                )}
              </Stack>
            </Collapse>
            <Typography color="text.secondary">{goals[goal].guidance}</Typography>
            <Stack direction="row" gap={1} flexWrap="wrap">
              {goals[goal].examples.map((example) => (
                <Chip
                  key={example}
                  label={example}
                  onClick={() => setQuestion(example)}
                  sx={{ height: 'auto', '& .MuiChip-label': { whiteSpace: 'normal', py: 1 } }}
                />
              ))}
            </Stack>
            <TextField
              label="Question"
              multiline
              minRows={3}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              inputProps={{ maxLength: 2000 }}
            />
            <Alert severity="info">
              Your question and result are stored privately and can be reviewed by administrators
              for operations and abuse prevention. Other users cannot see them.
            </Alert>
            <Button onClick={() => setAdvanced((value) => !value)} aria-expanded={advanced}>
              Advanced settings
            </Button>
            <Collapse in={advanced}>
              <FormControl fullWidth>
                <InputLabel>Filing Items (all when omitted)</InputLabel>
                <Select
                  multiple
                  label="Filing Items (all when omitted)"
                  value={allowed}
                  renderValue={(selected) => selected.map((value) => `Item ${value}`).join(', ')}
                  onChange={(event) =>
                    setAllowed(
                      typeof event.target.value === 'string'
                        ? event.target.value.split(',')
                        : event.target.value,
                    )
                  }
                >
                  {items.map((item) => (
                    <MenuItem key={item} value={item}>
                      <Checkbox checked={allowed.includes(item)} />
                      <ListItemText primary={`Item ${item}`} />
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Collapse>
            <Button
              variant="contained"
              size="large"
              disabled={!question.trim() || !corpus || Boolean(stage) || !canResearch}
              onClick={() => void submit()}
            >
              Run query
            </Button>
            {!canResearch && (
              <Alert severity="warning">
                Your remaining lifetime allowance is below the amount required for a query. Existing
                queries and Library filings remain available.
              </Alert>
            )}
            {stage && (
              <Alert severity="info" aria-live="polite">
                {stage.replace('_', ' ')}… Server-side work continues if this tab closes.
              </Alert>
            )}
          </Stack>
        </Paper>
        {evidence.length > 0 && (
          <Box>
            <Typography variant="h2">Sources found</Typography>
            {evidence.map((source) => (
              <Paper key={source.chunk_id} sx={{ p: 2, mt: 1 }}>
                <Typography variant="subtitle2">
                  Item {source.item} · {source.citation_handle}
                </Typography>
                <Typography>{source.excerpt}</Typography>
              </Paper>
            ))}
          </Box>
        )}
        <Box>
          <Stack direction="row" justifyContent="space-between">
            <Typography variant="h2">Recent queries</Typography>
            <Button onClick={() => void navigate('/research/history')}>View history</Button>
          </Stack>
          {recent.map((run) => (
            <Button
              key={run.research_id}
              onClick={() => void navigate(`/research/${run.research_id}`)}
              sx={{ display: 'block', textAlign: 'left' }}
            >
              {run.ticker} · {run.question}
            </Button>
          ))}
        </Box>
      </Stack>
    </AppShell>
  );
}
