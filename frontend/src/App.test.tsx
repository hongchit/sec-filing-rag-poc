import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, vi, test, expect } from 'vitest';
import { ThemeProvider } from '@mui/material/styles';
import { App } from './App';
import { theme } from './theme';
import { Help } from './components/Help';
import { normalizedRoute } from './analytics';

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
beforeEach(() => vi.stubGlobal('ResizeObserver', ResizeObserverMock));
const renderApp = () =>
  render(
    <ThemeProvider theme={theme}>
      <App />
    </ThemeProvider>,
  );

test('redirects the root route to the research workspace', () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => new Promise(() => {})),
  );
  renderApp();
  expect(screen.getByRole('heading', { name: 'Investor research' })).toBeInTheDocument();
});

test('bootstraps latest filings when a fresh installation has no active corpus', async () => {
  history.replaceState(null, '', '/research');
  let statusReads = 0;
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    let body: unknown;
    if (url === '/api/auth/me')
      body = {
        user_id: 'user-id',
        email: 'user@example.com',
        is_admin: false,
        budget: { limit_usd: '10', used_usd: '0', reserved_usd: '0', remaining_usd: '10' },
        action_reservations: { research_usd: '0.05', corpus_preparation_usd: '0.05' },
      };
    else if (url === '/api/companies') body = [{ ticker: 'AAPL', enabled: true, name: 'Apple' }];
    else if (url === '/api/companies/AAPL/status') {
      statusReads += 1;
      body = {
        ticker: 'AAPL',
        active_corpus:
          statusReads > 1
            ? {
                corpus_version_id: 'corpus-latest',
                accession: '0000320193-25-000079',
                report_date: '2025-09-27',
                filing_date: '2025-10-31',
              }
            : null,
        historical_corpora: [],
      };
    } else if (url === '/api/research/history?limit=10') body = { items: [] };
    else if (url === '/api/filing-batches' && init?.method === 'POST')
      body = { batch_id: 'batch-id' };
    else if (url === '/api/filing-batches/batch-id')
      body = { status: 'succeeded', items: [{ status: 'succeeded' }] };
    else body = {};
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  });
  vi.stubGlobal('fetch', fetchMock);

  render(
    <ThemeProvider theme={theme}>
      <App authenticate />
    </ThemeProvider>,
  );

  fireEvent.click(await screen.findByRole('button', { name: 'Prepare latest filings' }));
  await waitFor(() => expect(screen.getByText('Latest filings ready.')).toBeInTheDocument());
  expect(
    fetchMock.mock.calls.some(
      ([input, init]) =>
        input === '/api/filing-batches' &&
        init?.method === 'POST' &&
        init.body === JSON.stringify({}),
    ),
  ).toBe(true);
  await waitFor(() =>
    expect(screen.queryByText('No searchable filing corpus is ready yet.')).not.toBeInTheDocument(),
  );
  expect(screen.getAllByRole('combobox')[0]).toHaveTextContent('AAPL');
  expect(screen.getAllByRole('combobox')[1]).toHaveTextContent('2025');
});

test('keeps successful corpora available when latest bootstrap partially fails', async () => {
  history.replaceState(null, '', '/research');
  let refreshed = false;
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      let body: unknown;
      if (url === '/api/auth/me')
        body = {
          user_id: 'user-id',
          email: 'user@example.com',
          is_admin: false,
          budget: { limit_usd: '10', used_usd: '0', reserved_usd: '0', remaining_usd: '10' },
          action_reservations: { research_usd: '0.05', corpus_preparation_usd: '0.05' },
        };
      else if (url === '/api/companies')
        body = [
          { ticker: 'AAPL', enabled: true },
          { ticker: 'MSFT', enabled: true },
        ];
      else if (url.endsWith('/status'))
        body = {
          ticker: url.includes('AAPL') ? 'AAPL' : 'MSFT',
          active_corpus:
            refreshed && url.includes('AAPL')
              ? {
                  corpus_version_id: 'corpus-aapl',
                  accession: 'accession',
                  report_date: '2025-09-27',
                  filing_date: '2025-10-31',
                }
              : null,
          historical_corpora: [],
        };
      else if (url === '/api/research/history?limit=10') body = { items: [] };
      else if (url === '/api/filing-batches' && init?.method === 'POST')
        body = { batch_id: 'partial-batch' };
      else if (url === '/api/filing-batches/partial-batch') {
        refreshed = true;
        body = {
          status: 'partial_failure',
          items: [
            { status: 'succeeded' },
            { status: 'failed', safe_error: 'MSFT filing preparation failed safely.' },
          ],
        };
      } else body = {};
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
    }),
  );

  render(
    <ThemeProvider theme={theme}>
      <App authenticate />
    </ThemeProvider>,
  );
  fireEvent.click(await screen.findByRole('button', { name: 'Prepare latest filings' }));

  expect(await screen.findByText('MSFT filing preparation failed safely.')).toBeInTheDocument();
  await waitFor(() => expect(screen.getAllByRole('combobox')[1]).toHaveTextContent('2025'));
  expect(screen.queryByText('No searchable filing corpus is ready yet.')).not.toBeInTheDocument();
});

test('keeps policies public and sends protected routes to the landing page', async () => {
  history.replaceState(null, '', '/privacy');
  const fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  const view = render(
    <ThemeProvider theme={theme}>
      <App authenticate />
    </ThemeProvider>,
  );
  expect(screen.getByRole('heading', { name: 'Privacy Policy' })).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
  view.unmount();

  history.replaceState(null, '', '/research');
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ ok: false })),
  );
  render(
    <ThemeProvider theme={theme}>
      <App authenticate />
    </ThemeProvider>,
  );
  expect(
    await screen.findByRole('heading', {
      name: 'Understand annual filings without reading every page.',
    }),
  ).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Sign in with Google' })).toHaveAttribute(
    'href',
    expect.stringContaining('policy_acknowledged=true'),
  );
});

test('normalizes sensitive route values before analytics', () => {
  expect(normalizedRoute('/research/1ea094c5-79b5-4c75-a0a1-5715db1a4e48')).toBe(
    '/research/:researchId',
  );
  expect(normalizedRoute('/corpus/AAPL/1')).toBe('/corpus/:ticker/:item');
  expect(normalizedRoute('/unknown/private-value')).toBe('/other');
});

test('help popovers dismiss with Escape and outside click', async () => {
  render(
    <ThemeProvider theme={theme}>
      <Help term="top-k">Highest-ranked chunks checked.</Help>
    </ThemeProvider>,
  );
  const trigger = screen.getByRole('button', { name: 'Help: top-k' });
  fireEvent.click(trigger);
  expect(screen.getByText('Highest-ranked chunks checked.')).toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole('presentation'), { key: 'Escape' });
  await waitFor(() =>
    expect(screen.queryByText('Highest-ranked chunks checked.')).not.toBeInTheDocument(),
  );
  fireEvent.click(trigger);
  fireEvent.click(document.querySelector('.MuiBackdrop-root')!);
  await waitFor(() =>
    expect(screen.queryByText('Highest-ranked chunks checked.')).not.toBeInTheDocument(),
  );
});

test('retrying failed research restores its query and advanced settings', async () => {
  const researchId = '1ea094c5-79b5-4c75-a0a1-5715db1a4e48';
  const failedResearch = {
    research_id: researchId,
    ticker: 'AAPL',
    corpus_version_id: 'corpus-2024',
    goal: 'key_risks',
    question: 'Which supplier dependencies create risk?',
    allowed_items: ['1A', '7'],
    status: 'failed',
    safe_error: 'Provider operation failed.',
  };
  history.replaceState(null, '', `/research/${researchId}`);
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      const body =
        url === `/api/research/${researchId}`
          ? failedResearch
          : url === '/api/companies'
            ? [{ ticker: 'AAPL', enabled: true, name: 'Apple' }]
            : url === '/api/companies/AAPL/status'
              ? {
                  ticker: 'AAPL',
                  active_corpus: {
                    corpus_version_id: 'corpus-2024',
                    accession: '0000320193-24-000123',
                    report_date: '2024-09-28',
                    filing_date: '2024-11-01',
                  },
                  historical_corpora: [],
                }
              : { items: [] };
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
    }),
  );

  renderApp();
  fireEvent.click(await screen.findByRole('button', { name: 'Retry as new research' }));

  expect(await screen.findByDisplayValue(failedResearch.question)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Advanced settings' })).toHaveAttribute(
    'aria-expanded',
    'true',
  );
  await waitFor(() => expect(screen.getByText('Key Risks')).toBeInTheDocument());
  await waitFor(() => {
    const selects = screen.getAllByRole('combobox');
    expect(selects[0]).toHaveTextContent('AAPL');
    expect(selects[1]).toHaveTextContent('2024');
    expect(selects[3]).toHaveTextContent('Item 1A, Item 7');
  });
});

test('shows interpretation paragraphs before filing facts while preserving group order', async () => {
  const researchId = '2ea094c5-79b5-4c75-a0a1-5715db1a4e48';
  history.replaceState(null, '', `/research/${researchId}`);
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            research_id: researchId,
            ticker: 'AAPL',
            corpus_version_id: 'corpus-2024',
            goal: 'key_risks',
            question: 'What risks matter?',
            allowed_items: null,
            status: 'succeeded',
            answer: [
              { text: 'Fact one', kind: 'filing_fact', citations: [] },
              { text: 'Interpretation one', kind: 'interpretation', citations: [] },
              { text: 'Fact two', kind: 'filing_fact', citations: [] },
              { text: 'Interpretation two', kind: 'interpretation', citations: [] },
            ],
            limitations: [],
            insufficient_evidence: false,
            disposition: 'answered',
            estimate_status: 'available',
            evidence: [],
            usage: {
              query_embedding_input: 1,
              answer_generation_input: 1,
              answer_generation_output: 1,
              complete_request_total: 3,
              provider_calls: 1,
            },
            run_details: { accession: '0000320193-24-000123' },
            created_at: '2026-01-01T00:00:00Z',
          }),
      }),
    ),
  );

  renderApp();
  const paragraphs = await screen.findAllByText(/^(Interpretation|Fact) (one|two)$/);
  expect(paragraphs.map((paragraph) => paragraph.textContent)).toEqual([
    'Interpretation one',
    'Interpretation two',
    'Fact one',
    'Fact two',
  ]);
});

test('links administrators to research results in a user activity record', async () => {
  const userId = '3ea094c5-79b5-4c75-a0a1-5715db1a4e48';
  const researchId = '4ea094c5-79b5-4c75-a0a1-5715db1a4e48';
  history.replaceState(null, '', `/admin?user=${userId}`);
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const body =
      url === '/api/admin/users'
        ? {
            items: [
              {
                id: userId,
                email: 'user@example.com',
                status: 'active',
                budget: {
                  limit_usd: '10.00',
                  used_usd: '0.10',
                  reserved_usd: '0.00',
                  remaining_usd: '9.90',
                },
              },
            ],
          }
        : {
            research: [
              {
                id: researchId,
                ticker: 'AAPL',
                question: 'What risks matter?',
                status: 'succeeded',
                charged_usd: '0.01',
              },
            ],
            filing_batches: [
              {
                id: '5ea094c5-79b5-4c75-a0a1-5715db1a4e48',
                mode: 'exact_year',
                fiscal_year: 2024,
                status: 'succeeded',
                charged_usd: '0.02',
                kestra_execution_id: 'execution-123',
                items: [
                  {
                    id: '6ea094c5-79b5-4c75-a0a1-5715db1a4e48',
                    ticker: 'AAPL',
                    status: 'succeeded',
                    selected_accession: '0000320193-24-000123',
                    corpus_version_id: '7ea094c5-79b5-4c75-a0a1-5715db1a4e48',
                  },
                ],
              },
              {
                id: '8ea094c5-79b5-4c75-a0a1-5715db1a4e48',
                mode: 'exact_year',
                fiscal_year: 1999,
                status: 'failed',
                items: [
                  {
                    id: '9ea094c5-79b5-4c75-a0a1-5715db1a4e48',
                    ticker: 'AAPL',
                    status: 'skipped',
                    safe_error: 'no original 10-K for fiscal year 1999',
                  },
                ],
              },
            ],
          };
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  });
  vi.stubGlobal('fetch', fetchMock);

  renderApp();
  fireEvent.click(await screen.findByRole('button', { name: /user@example.com/ }));

  expect(location.pathname).toBe('/admin/users');
  expect(location.search).toBe(`?user=${userId}`);
  expect(
    screen.queryByRole('heading', { name: 'Operational model executions' }),
  ).not.toBeInTheDocument();
  expect(
    fetchMock.mock.calls.some(([input]) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      return url.includes('/model-executions');
    }),
  ).toBe(false);
  expect(await screen.findByRole('link', { name: 'What risks matter?' })).toHaveAttribute(
    'href',
    `/research/${researchId}`,
  );
  expect(screen.getByText(/^1\. AAPL/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'AAPL' })).toHaveAttribute(
    'href',
    '/corpus/AAPL/1?corpus=7ea094c5-79b5-4c75-a0a1-5715db1a4e48',
  );
  expect(screen.getByText(/2\. exact_year 1999 · skipped/)).toBeInTheDocument();
  expect(screen.getByText('no original 10-K for fiscal year 1999')).toBeInTheDocument();
  expect(screen.getByText('Kestra execution: execution-123')).toBeInTheDocument();
});

test('shows operational executions separately without loading users', async () => {
  history.replaceState(null, '', '/admin/model-executions');
  const fetchMock = vi.fn(() =>
    Promise.resolve({
      ok: true,
      json: () =>
        Promise.resolve({
          items: [
            {
              run_type: 'ground_truth_generation',
              id: '10a094c5-79b5-4c75-a0a1-5715db1a4e48',
              status: 'succeeded',
              started_at: '2026-01-01T00:00:00Z',
              finished_at: '2026-01-01T00:01:00Z',
              models: ['gpt-5.4-mini'],
              operations: [],
              provider_calls: 1,
              retries: 0,
              failures: 0,
              input_tokens: 100,
              output_tokens: 50,
              total_tokens: 150,
              usage_available: true,
              estimated_usd: '0.001',
              pricing_basis: 'stored_snapshot',
            },
          ],
          next_offset: null,
        }),
    }),
  );
  vi.stubGlobal('fetch', fetchMock);

  renderApp();

  expect(
    await screen.findByRole('heading', { name: 'Operational model executions' }),
  ).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Users' })).not.toBeInTheDocument();
  expect(screen.getByText(/ground truth generation · succeeded/)).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock).toHaveBeenCalledWith('/api/admin/model-executions?limit=25&offset=0');
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  history.replaceState(null, '', '/');
});

test('renders the selected evaluation winner and question evidence', async () => {
  history.replaceState(null, '', '/evaluation?outcome=miss');
  const summary = {
    run: { status: 'succeeded', question_count: 1, finished_at: '2026-01-01T00:00:00Z' },
    coverage: { accepted_questions: 1 },
    warnings: [],
    selected_default_id: 'cfg-win',
    strategy_best: {
      keyword: 'cfg-win',
      vector: 'cfg-vector',
      weighted_hybrid: 'cfg-hybrid',
      rrf: 'cfg-rrf',
    },
    lineage: { dataset_sha256: 'abc' },
    configurations: [
      {
        id: 'cfg-win',
        official_rank: 1,
        selected: true,
        strategy: 'keyword',
        candidate_count: 10,
        top_k: 5,
        alpha: 0.5,
        rrf_k: 60,
        hit_rate: 1,
        mrr: 1,
        median_latency_ms: 2,
      },
      {
        id: 'cfg-vector',
        official_rank: 2,
        selected: false,
        strategy: 'vector',
        candidate_count: 10,
        top_k: 5,
        alpha: 0.5,
        rrf_k: 60,
        hit_rate: 0.9,
        mrr: 0.8,
        median_latency_ms: 3,
      },
      {
        id: 'cfg-hybrid',
        official_rank: 3,
        selected: false,
        strategy: 'weighted_hybrid',
        candidate_count: 10,
        top_k: 5,
        alpha: 0.25,
        rrf_k: 60,
        hit_rate: 0.9,
        mrr: 0.8,
        median_latency_ms: 4,
      },
      {
        id: 'cfg-rrf',
        official_rank: 4,
        selected: false,
        strategy: 'rrf',
        candidate_count: 10,
        top_k: 5,
        alpha: 0.5,
        rrf_k: 60,
        hit_rate: 0.8,
        mrr: 0.7,
        median_latency_ms: 5,
      },
    ],
  };
  const cases = {
    configuration_id: 'cfg-win',
    warnings: [],
    facets: {
      tickers: ['AAPL'],
      items: ['1'],
      goals: ['business'],
      query_types: ['exact_keyword'],
    },
    cases: [
      {
        id: 'q1',
        question: 'What is the business?',
        ticker: 'AAPL',
        items: ['1'],
        goal: 'business',
        query_type: 'exact_keyword',
        accession: 'x',
        outcome: 'miss',
        first_relevant_rank: null,
        expected: [],
        retrieved: [],
      },
    ],
  };
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(url.endsWith('/cases') ? cases : summary),
      }),
    ),
  );
  renderApp();
  expect(
    await screen.findByRole('heading', { name: 'Keyword leads this benchmark' }),
  ).toBeInTheDocument();
  expect(await screen.findByText('What is the business?')).toBeInTheDocument();
  await waitFor(() => expect(location.search).toContain('outcome=miss'));
});

test('uses a single-open ranked evidence panel and replaces the selected chunk inspector', async () => {
  history.replaceState(
    null,
    '',
    '/evaluation/configurations/cfg/questions/one?configuration=cfg&outcome=later_hit&page=1',
  );
  const configuration = {
    id: 'cfg',
    official_rank: 1,
    selected: true,
    strategy: 'keyword',
    candidate_count: 10,
    top_k: 5,
    alpha: 0.5,
    rrf_k: 60,
    hit_rate: 0.5,
    mrr: 0.4,
    median_latency_ms: 2,
  };
  const summary = {
    run: { status: 'succeeded', question_count: 2 },
    coverage: {},
    warnings: [],
    selected_default_id: 'cfg',
    strategy_best: { keyword: 'cfg' },
    lineage: {},
    configurations: [configuration],
  };
  const chunk = (id: string, rank: number) => ({
    chunk_id: id,
    citation: `AAPL 10-K · Item 1 · ${id}`,
    missing: false,
    rank,
    matched: rank === 1,
    preview: `Preview for ${id} with enough text for the compact evidence card.`,
    ticker: 'AAPL',
    item: '1',
    accession: 'x',
    source_url: 'https://www.sec.gov/example',
  });
  const makeCase = (id: string, retrieved: ReturnType<typeof chunk>[]) => ({
    id,
    question: `Question ${id}`,
    ticker: 'AAPL',
    items: ['1'],
    goal: 'business',
    query_type: 'literal',
    accession: 'x',
    outcome: 'later_hit' as const,
    first_relevant_rank: 2,
    expected: [],
    retrieved,
  });
  const cases = {
    configuration_id: 'cfg',
    warnings: [],
    facets: { tickers: ['AAPL'], items: ['1'], goals: ['business'], query_types: ['literal'] },
    cases: [
      makeCase('one', [chunk('first', 1), chunk('second', 2)]),
      makeCase('two', [chunk('third', 1)]),
    ],
  };
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve(
            url.endsWith('/cases')
              ? cases
              : url.includes('/chunks/')
                ? {
                    ...chunk(url.split('/').pop()!, 1),
                    text: `Full text ${url.split('/').pop()}`,
                    provenance: { checksum: 'safe' },
                  }
                : summary,
          ),
      }),
    ),
  );
  renderApp();
  expect(await screen.findByRole('heading', { name: 'Question one' })).toHaveFocus();
  expect(screen.queryByRole('separator')).not.toBeInTheDocument();
  expect(screen.getAllByTestId('ranked-evidence-panel')).toHaveLength(1);
  expect(screen.queryByText(/Drag to resize|\d+px/)).not.toBeInTheDocument();
  expect(screen.getByText('AAPL 10-K · Item 1 · first')).toBeInTheDocument();
  expect(
    screen.getByText('Preview for first with enough text for the compact evidence card.'),
  ).toBeInTheDocument();
  expect(
    screen.getByText('Preview for second with enough text for the compact evidence card.'),
  ).not.toBeVisible();
  fireEvent.click(screen.getByText('AAPL 10-K · Item 1 · second'));
  await waitFor(() =>
    expect(
      screen.getByText('Preview for first with enough text for the compact evidence card.'),
    ).not.toBeVisible(),
  );
  const actions = screen.getAllByRole('button', { name: 'Read full text & provenance' });
  fireEvent.click(actions[0]);
  expect(
    await screen.findByRole('heading', { name: 'Selected chunk: AAPL 10-K · Item 1 · second' }),
  ).toHaveFocus();
  fireEvent.click(screen.getByText('AAPL 10-K · Item 1 · first'));
  await waitFor(() =>
    expect(
      screen.getByText('Preview for first with enough text for the compact evidence card.'),
    ).toBeVisible(),
  );
  fireEvent.click(
    screen
      .getAllByRole('button', { name: 'Read full text & provenance' })
      .find((button) => button.getAttribute('aria-pressed') === 'false')!,
  );
  expect(
    await screen.findByRole('heading', { name: 'Selected chunk: AAPL 10-K · Item 1 · first' }),
  ).toHaveFocus();
  expect(
    screen.queryByRole('heading', { name: 'Selected chunk: AAPL 10-K · Item 1 · second' }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Back to questions' })).toHaveAttribute(
    'href',
    '/evaluation?configuration=cfg&outcome=later_hit&page=1',
  );
  expect(screen.getByRole('link', { name: 'Next question' })).toHaveAttribute(
    'href',
    expect.stringContaining('/questions/two?'),
  );
});
