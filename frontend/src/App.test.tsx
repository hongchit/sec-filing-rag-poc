import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, vi, test, expect } from 'vitest';
import { ThemeProvider } from '@mui/material/styles';
import { App } from './App';
import { theme } from './theme';
import { Help } from './components/Help';
import { EvaluationTerm } from './components/EvaluationTerm';
import { normalizedRoute } from './analytics';
import { safeLocalReturnTo } from './returnTo';
import { preparationSubmissionMessage } from './preparationErrors';

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

test('explains filing-preparation submission failures', async () => {
  const response = (status: number, detail: object) => ({
    status,
    json: () => Promise.resolve({ detail }),
  });

  await expect(
    preparationSubmissionMessage(response(403, { code: 'quota_exceeded' })),
  ).resolves.toMatch(/allowance is too low/);
  await expect(
    preparationSubmissionMessage(response(403, { code: 'invalid_csrf' })),
  ).resolves.toMatch(/Sign out, sign in/);
  await expect(preparationSubmissionMessage(response(502, {}))).resolves.toMatch(/Kestra/);
});

test('renders the public landing page at the root route', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      return Promise.resolve({
        ok: url === '/api/showcase',
        json: () => Promise.resolve(url === '/api/showcase' ? { examples: [] } : {}),
      });
    }),
  );
  renderApp();
  expect(
    await screen.findByRole('heading', {
      name: 'Ask an annual report a question. Get a cited answer.',
    }),
  ).toBeInTheDocument();
});

test('renders configured showcase examples in order and prefills Query', async () => {
  const examples = [
    {
      id: 'first',
      question: 'What was cloud revenue?',
      answer: 'Cloud revenue was $137.4 billion.',
      ticker: 'MSFT',
      filing_period: 'Fiscal year 2024',
      accession: '0000950170-24-087843',
      items: ['7'],
      citations: ['0000950170-24-087843:item-7:0000'],
      goal: 'management_analysis',
    },
    {
      id: 'second',
      question: 'Which products form the platform?',
      answer: 'The platform combines hardware and software.',
      ticker: 'NVDA',
      filing_period: 'Fiscal year 2024',
      accession: '0001045810-24-000029',
      items: ['1'],
      citations: ['0001045810-24-000029:item-1:0005'],
      goal: 'business',
    },
  ];
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      return Promise.resolve({
        ok: url === '/api/showcase',
        json: () => Promise.resolve(url === '/api/showcase' ? { examples } : {}),
      });
    }),
  );

  renderApp();

  expect(await screen.findByText('What was cloud revenue?')).toBeInTheDocument();
  const action = screen.getByRole('link', { name: 'Try this question in Query' });
  expect(action).toHaveAttribute('href', expect.stringContaining('company%3DMSFT'));
  fireEvent.click(screen.getByRole('button', { name: 'Next example' }));
  expect(screen.getByText('Which products form the platform?')).toBeInTheDocument();
  expect(screen.getByText('Example 2 of 2')).toBeInTheDocument();
});

test('accepts only safe local return destinations', () => {
  expect(safeLocalReturnTo('/evaluation/answer-quality/questions?company=AAPL')).toBe(
    '/evaluation/answer-quality/questions?company=AAPL',
  );
  expect(safeLocalReturnTo('https://example.com/private')).toBe('/research');
  expect(safeLocalReturnTo('//example.com/private')).toBe('/research');
});

test('redirects an authenticated visitor away from the sign-in page', async () => {
  history.replaceState(null, '', '/sign-in?return_to=%2Foverview');
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            user_id: 'user-id',
            email: 'user@example.com',
            is_admin: false,
            budget: { limit_usd: '10', used_usd: '0', reserved_usd: '0', remaining_usd: '10' },
            action_reservations: { research_usd: '0.05', corpus_preparation_usd: '0.05' },
          }),
      }),
    ),
  );
  renderApp();
  expect(
    await screen.findByRole('heading', {
      name: 'Give a language model the evidence it needs, when it needs it.',
    }),
  ).toBeInTheDocument();
});

test('redirects a guest Data route before requesting evaluation data', async () => {
  history.replaceState(null, '', '/evaluation/evidence-search/questions?outcome=miss');
  const fetchMock = vi.fn((url: string) =>
    Promise.resolve({
      ok: false,
      json: () => Promise.resolve(url === '/api/showcase' ? { examples: [] } : {}),
    }),
  );
  vi.stubGlobal('fetch', fetchMock);
  render(
    <ThemeProvider theme={theme}>
      <App authenticate />
    </ThemeProvider>,
  );
  expect(
    await screen.findByRole('heading', {
      name: 'Sign in required',
    }),
  ).toBeInTheDocument();
  expect(window.location.search).toContain('return_to=%2Fevaluation%2Fevidence-search%2Fquestions');
  expect(screen.getByRole('link', { name: 'Continue with Google' })).toHaveAttribute(
    'href',
    expect.stringContaining(
      'return_to=%2Fevaluation%2Fevidence-search%2Fquestions%3Foutcome%3Dmiss',
    ),
  );
  expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/cases'))).toBe(false);
});

test('checks authentication once while navigating public routes', async () => {
  const fetchMock = vi.fn((url: string) =>
    Promise.resolve({
      ok: false,
      json: () => Promise.resolve(url === '/api/showcase' ? { examples: [] } : {}),
    }),
  );
  vi.stubGlobal('fetch', fetchMock);
  renderApp();
  fireEvent.click(await screen.findByRole('link', { name: 'Why use RAG?' }));
  await screen.findByRole('heading', { name: 'LLM alone vs RAG' });
  fireEvent.click(screen.getByRole('link', { name: 'How it works' }));
  await screen.findByRole('heading', { name: 'A basic RAG implementation, measured end to end.' });
  expect(fetchMock.mock.calls.filter(([url]) => url === '/api/auth/me')).toHaveLength(1);
});

test('bootstraps latest filings when a fresh installation has no active filing collection', async () => {
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
    expect(
      screen.queryByText('No searchable filing is ready in the Library yet.'),
    ).not.toBeInTheDocument(),
  );
  expect(screen.getAllByRole('combobox')[0]).toHaveTextContent('AAPL');
  expect(screen.getAllByRole('combobox')[1]).toHaveTextContent('2025');
  expect(screen.getByRole('link', { name: 'Query' })).toHaveAttribute('href', '/research');
  expect(screen.getByRole('link', { name: 'Library' })).toHaveAttribute('href', '/corpus');
  expect(
    screen
      .getByRole('link', { name: 'How it works' })
      .querySelector('[data-testid="AccountTreeOutlinedIcon"]'),
  ).toBeInTheDocument();
});

test('keeps successful filing collections available when latest bootstrap partially fails', async () => {
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
  expect(
    screen.queryByText('No searchable filing is ready in the Library yet.'),
  ).not.toBeInTheDocument();
});

test('keeps policies public and sends protected routes to the sign-in page', async () => {
  history.replaceState(null, '', '/privacy');
  const fetchMock = vi.fn(() => Promise.resolve({ ok: false }));
  vi.stubGlobal('fetch', fetchMock);
  const view = render(
    <ThemeProvider theme={theme}>
      <App authenticate />
    </ThemeProvider>,
  );
  expect(await screen.findByRole('heading', { name: 'Privacy Policy' })).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
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
      name: 'Sign in required',
    }),
  ).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Continue with Google' })).toHaveAttribute(
    'href',
    expect.stringContaining('return_to=%2Fresearch'),
  );
  expect(screen.getByText(/Saved queries, filing documents/)).toBeInTheDocument();
});

test('normalizes sensitive route values before analytics', () => {
  expect(normalizedRoute('/research/1ea094c5-79b5-4c75-a0a1-5715db1a4e48')).toBe(
    '/research/:researchId',
  );
  expect(normalizedRoute('/corpus/AAPL/1')).toBe('/corpus/:ticker/:item');
  expect(normalizedRoute('/unknown/private-value')).toBe('/other');
  expect(normalizedRoute('/overview')).toBe('/overview');
  expect(normalizedRoute('/how-it-works')).toBe('/how-it-works');
  expect(normalizedRoute('/sign-in')).toBe('/sign-in');
  expect(normalizedRoute('/evaluation/evidence-search/questions')).toBe(
    '/evaluation/evidence-search/questions',
  );
});

test('renders the public LLM versus RAG comparison without the RAG-loop diagram', async () => {
  history.replaceState(null, '', '/overview');
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ ok: false })),
  );

  renderApp();

  expect(
    await screen.findByRole('heading', {
      name: 'Give a language model the evidence it needs, when it needs it.',
    }),
  ).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'LLM alone vs RAG' })).toBeInTheDocument();
  expect(screen.getByText('Relies on training memory')).toBeInTheDocument();
  expect(screen.getByText('Produces a cited answer')).toBeInTheDocument();
  expect(screen.queryByRole('img', { name: /RAG flow/i })).not.toBeInTheDocument();
});

test('shows the RAG loop and trusted data layers only on How It Works', async () => {
  history.replaceState(null, '', '/how-it-works');
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ ok: false })),
  );
  renderApp();
  expect(
    await screen.findByRole('img', { name: /filing preparation pipeline feeds an index/i }),
  ).toHaveAttribute('src', '/diagrams/rag-loop.svg');
  expect(
    screen.getByRole('heading', { name: 'Three data layers, each with one clear job.' }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole('img', { name: /bronze preserves the original filing/i }),
  ).toHaveAttribute('src', '/diagrams/medallion-data-layers.svg');
  expect(screen.getByRole('heading', { name: 'Bronze — Preserve the source' })).toBeInTheDocument();
  expect(
    screen.getByRole('heading', { name: 'Silver — Build trusted knowledge' }),
  ).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Gold — Search efficiently' })).toBeInTheDocument();
  expect(
    screen.getByRole('heading', { name: 'Future improvements for richer research' }),
  ).toBeInTheDocument();
  expect(screen.getByText('Structured table understanding')).toBeInTheDocument();
  expect(screen.getByText('Image and chart understanding')).toBeInTheDocument();
  expect(
    screen.getByText(/Only the strongest evidence reaches the answer model/),
  ).toBeInTheDocument();
  expect(screen.getByText('Bounded agentic retrieval')).toBeInTheDocument();
  expect(screen.getByText('Knowledge graph retrieval')).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Glossary' })).not.toBeInTheDocument();
});

test('renders exactly three landing process steps without Verify', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve({
        ok: false,
        json: () => Promise.resolve(url === '/api/showcase' ? { examples: [] } : {}),
      }),
    ),
  );
  renderApp();
  expect(await screen.findByText('1. Ask')).toBeInTheDocument();
  expect(screen.getByText('2. Find evidence')).toBeInTheDocument();
  expect(screen.getByText('3. Answer')).toBeInTheDocument();
  expect(screen.queryByText('4. Verify')).not.toBeInTheDocument();
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

test('evaluation terms expose concise business definitions', () => {
  render(
    <ThemeProvider theme={theme}>
      <EvaluationTerm term="mrr">MRR</EvaluationTerm>
    </ThemeProvider>,
  );
  const trigger = screen.getByRole('button', { name: 'Help: MRR' });
  expect(trigger).toHaveAttribute('aria-haspopup', 'dialog');
  fireEvent.click(trigger);
  expect(screen.getByText(/how early the first relevant passage appears/i)).toBeInTheDocument();
  expect(trigger).toHaveAttribute('aria-expanded', 'true');
  expect(trigger).toHaveAttribute('aria-controls');
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
  fireEvent.click(await screen.findByRole('button', { name: 'Retry as new query' }));

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

test('prefills a benchmark question from validated research query parameters', async () => {
  history.replaceState(
    null,
    '',
    '/research?company=AAPL&goal=key_risks&items=1A%2C7&accession=0000320193-24-000123&question=Which+dependencies+create+risk%3F',
  );
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      const body =
        url === '/api/companies'
          ? [{ ticker: 'AAPL', enabled: true, name: 'Apple' }]
          : url === '/api/companies/AAPL/status'
            ? {
                ticker: 'AAPL',
                active_corpus: {
                  corpus_version_id: 'corpus-aapl',
                  accession: '0000320193-25-000079',
                  report_date: '2025-09-27',
                  filing_date: '2025-10-31',
                },
                historical_corpora: [
                  {
                    corpus_version_id: 'corpus-aapl-2024',
                    accession: '0000320193-24-000123',
                    report_date: '2024-09-28',
                    filing_date: '2024-11-01',
                  },
                ],
              }
            : { items: [] };
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
    }),
  );

  renderApp();

  expect(await screen.findByDisplayValue('Which dependencies create risk?')).toBeInTheDocument();
  await waitFor(() => expect(screen.getAllByRole('combobox')[0]).toHaveTextContent('AAPL'));
  expect(screen.getAllByRole('combobox')[1]).toHaveTextContent('2024');
  expect(screen.getAllByRole('combobox')[2]).toHaveTextContent('Key Risks');
  expect(screen.getAllByRole('combobox')[3]).toHaveTextContent('Item 1A, Item 7');
});

test('discloses when an evaluated filing prefill falls back to the latest filing', async () => {
  history.replaceState(
    null,
    '',
    '/research?company=AAPL&accession=unavailable&question=What+changed%3F',
  );
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      const body =
        url === '/api/companies'
          ? [{ ticker: 'AAPL', enabled: true, name: 'Apple' }]
          : url === '/api/companies/AAPL/status'
            ? {
                ticker: 'AAPL',
                active_corpus: {
                  corpus_version_id: 'corpus-aapl',
                  accession: 'latest',
                  report_date: '2025-09-27',
                  filing_date: '2025-10-31',
                },
                historical_corpora: [],
              }
            : { items: [] };
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
    }),
  );

  renderApp();

  expect(
    await screen.findByText(
      'The filing used in the evaluation is not available here. The latest available filing has been selected instead.',
    ),
  ).toBeInTheDocument();
  expect(screen.getAllByRole('combobox')[1]).toHaveTextContent('2025');
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
  expect(screen.getAllByText('TL;DR')).toHaveLength(2);
  expect(screen.queryByText('Filing fact')).not.toBeInTheDocument();
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
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(fetchMock).toHaveBeenCalledWith('/api/auth/me');
  expect(fetchMock).toHaveBeenCalledWith('/api/admin/model-executions?limit=25&offset=0');
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  history.replaceState(null, '', '/');
});

test('renders the public retrieval summary without fetching question evidence', async () => {
  history.replaceState(null, '', '/evaluation/evidence-search?outcome=miss');
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
  const fetchMock = vi.fn((url: string) =>
    Promise.resolve({
      ok: url !== '/api/auth/me',
      json: () => Promise.resolve(summary),
    }),
  );
  vi.stubGlobal('fetch', fetchMock);
  renderApp();
  expect(
    await screen.findByRole('heading', { name: 'Which search strategy finds the right passage?' }),
  ).toBeInTheDocument();
  expect(screen.queryByText('What is the business?')).not.toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining('/cases'));
  fireEvent.click(screen.getByRole('button', { name: 'Help: Top-k' }));
  expect(screen.getByText(/maximum number of highest-ranked passages/i)).toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole('presentation'), { key: 'Escape' });
  const navigation = await screen.findByRole('navigation', { name: 'Evaluation' });
  expect(navigation).toHaveTextContent(
    'Evaluation overviewRetrieval evaluationEvaluation QuestionsRAG evaluationRAG Answer Comparison',
  );
  expect(screen.getByText('Evaluation Questions').closest('a')).toHaveAttribute(
    'href',
    '/sign-in?return_to=%2Fevaluation%2Fevidence-search%2Fquestions',
  );
  expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
  expect(screen.queryByRole('navigation', { name: 'Breadcrumb' })).not.toBeInTheDocument();
});

test('renders the public benefit-led evaluation with model provenance and measured baselines', async () => {
  history.replaceState(null, '', '/evaluation');
  const overview = {
    benchmark: {
      question_count: 96,
      finished_at: '2026-08-31T03:04:45Z',
      human_reviewed: true,
    },
    retrieval: {
      selected_strategy: 'weighted_hybrid',
      selected_configuration_id: 'cfg-hybrid',
      hit_count: 95,
      question_count: 96,
      hit_rate: 95 / 96,
      mrr: 0.96,
      median_latency_ms: 6.5,
      rank_buckets: { rank_one: 90, rank_two_three: 5, rank_four_ten: 0, not_found: 1 },
      baselines: {
        keyword: {
          configuration_id: 'cfg-keyword',
          strategy: 'keyword',
          hit_count: 95,
          mrr: 0.951,
          rank_buckets: { rank_one: 88, rank_two_three: 7, rank_four_ten: 0, not_found: 1 },
          median_latency_ms: 2.1,
          configuration: {},
        },
        vector: {
          configuration_id: 'cfg-vector',
          strategy: 'vector',
          hit_count: 95,
          mrr: 0.85,
          rank_buckets: { rank_one: 75, rank_two_three: 15, rank_four_ten: 5, not_found: 1 },
          median_latency_ms: 4.5,
          configuration: {},
        },
      },
    },
    generation: {
      selected_prompt_id: 'basic-grounded-v2',
      promoted_prompt_id: 'basic-grounded-v2',
      question_count: 96,
      relevant_count: 95,
      partly_relevant_count: 1,
      non_relevant_count: 0,
      valid_citation_handles: 253,
      citation_handles: 253,
      median_latency_ms: 2100,
      generation_cost_per_answer_usd: '0.002',
      failures: 0,
    },
    models: [
      {
        stage: 'evidence_search',
        role: 'Question understanding and passage matching',
        active_model: 'text-embedding-3-small',
        evaluated_model: 'text-embedding-3-small',
        matches: true,
      },
      {
        stage: 'answer_generation',
        role: 'Grounded answer drafting',
        active_model: 'gpt-5.4-mini',
        evaluated_model: 'gpt-5.4-mini',
        matches: true,
      },
      {
        stage: 'answer_judging',
        role: 'Consistent answer-quality measurement',
        active_model: null,
        evaluated_model: 'gpt-5.4-mini',
        matches: null,
      },
    ],
    example: {
      case_id: 'q1',
      question: 'What risks affect the supply chain?',
      ticker: 'AAPL',
      accession: '0000320193-24-000123',
      corpus_version_id: 'corpus-aapl-2024',
      items: ['1A'],
      goal: 'key_risks',
      query_type: 'semantic_paraphrase',
      consensus: true,
      interpretation: 'Supplier concentration can make component availability less resilient.',
      citations: ['0000320193-24-000123:item-1a:0001'],
      prompt_id: 'basic-grounded-v2',
      judge_label: 'RELEVANT',
    },
    warnings: [],
  };
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      return Promise.resolve({
        ok: url === '/api/evaluation-overview/current',
        json: () => Promise.resolve(overview),
      });
    }),
  );

  renderApp();

  expect(
    await screen.findByRole('heading', {
      name: 'Measured before it was trusted.',
    }),
  ).toBeInTheDocument();
  expect(screen.getByText('90 of 96')).toBeInTheDocument();
  expect(
    screen.getByRole('heading', { name: 'Different models handle different stages' }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole('heading', { name: 'Find relevant filing passages' }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole('heading', { name: 'Generate an answer from retrieved evidence' }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole('heading', { name: 'Measure answer relevance consistently' }),
  ).toBeInTheDocument();
  expect(screen.getAllByText('Selection considerations')).toHaveLength(3);
  expect(screen.getAllByText('Model used')).toHaveLength(3);
  expect(screen.getAllByText('Strengths and benefits')).toHaveLength(3);
  expect(screen.getAllByText('gpt-5.4-mini')).toHaveLength(2);
  expect(screen.getByRole('link', { name: 'Try this question in Query' })).toHaveAttribute(
    'href',
    expect.stringContaining('question=What+risks+affect+the+supply+chain%3F'),
  );
  expect(screen.getByText(/tested and tuned before it was made available/)).toBeInTheDocument();
});

test('renders portable generation results and missing-database recovery guidance', async () => {
  history.replaceState(null, '', '/evaluation/answer-quality?attention=needs_attention');
  const summary = {
    run: {
      status: 'succeeded',
      question_count: 1,
      prompt_count: 2,
      finished_at: '2026-08-31T03:04:45Z',
      generation_model: 'gpt-test',
      judge_model: 'gpt-test',
    },
    selected_prompt_id: 'basic-grounded-v2',
    promoted_prompt_id: 'basic-grounded-v2',
    availability: {
      artifact_loaded: true,
      audit_record_available: false,
      evidence_available: false,
    },
    warnings: [
      {
        code: 'evidence_unavailable',
        message: 'Generated answers remain reviewable, but filing evidence is unavailable.',
        recovery_docs: ['docs/getting-started.md', 'docs/rag-evaluation-workflow.md'],
      },
    ],
    lineage: {},
    prompts: [
      {
        id: 'basic-grounded-v2',
        official_rank: 1,
        selected: true,
        promoted: true,
        eligible: true,
        mean_score: 2,
        relevant_count: 1,
        partly_relevant_count: 0,
        non_relevant_count: 0,
        failures: 0,
        valid_citation_handles: 2,
        citation_handles: 2,
        cross_corpus_citations: 0,
        median_latency_ms: 2100,
        generation_cost_per_answer_usd: '0.002',
        judge_cost_per_answer_usd: '0.001',
      },
      {
        id: 'guardrailed-10k-v3',
        official_rank: 2,
        selected: false,
        promoted: false,
        eligible: true,
        mean_score: 1,
        relevant_count: 0,
        partly_relevant_count: 1,
        non_relevant_count: 0,
        failures: 0,
        valid_citation_handles: 1,
        citation_handles: 1,
        cross_corpus_citations: 0,
        median_latency_ms: 1800,
        generation_cost_per_answer_usd: '0.001',
        judge_cost_per_answer_usd: '0.001',
      },
    ],
  };
  const cases = {
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
        results: [
          {
            prompt_id: 'basic-grounded-v2',
            label: 'RELEVANT',
            failure: null,
            citations_valid: true,
            latency_ms: 2100,
          },
          {
            prompt_id: 'guardrailed-10k-v3',
            label: 'PARTLY_RELEVANT',
            failure: null,
            citations_valid: true,
            latency_ms: 1800,
          },
        ],
      },
    ],
  };
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve({
        ok: url !== '/api/auth/me',
        json: () => Promise.resolve(url.endsWith('/cases') ? cases : summary),
      }),
    ),
  );

  renderApp();

  expect(
    await screen.findByRole('heading', { name: 'Which prompt produces the strongest answers?' }),
  ).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Open RAG Evaluation Data' })).toHaveAttribute(
    'href',
    '/evaluation/answer-quality/questions',
  );
});

test('uses a single-open ranked evidence panel and replaces the selected chunk inspector', async () => {
  history.replaceState(
    null,
    '',
    '/evaluation/evidence-search/configurations/cfg/questions/one?configuration=cfg&outcome=later_hit&page=1',
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
  await waitFor(() => expect(screen.getByRole('heading', { name: 'Question one' })).toHaveFocus());
  expect(screen.getByRole('link', { name: 'Try this question in Query' })).toHaveAttribute(
    'href',
    expect.stringContaining('accession=x'),
  );
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
  expect(screen.getByRole('link', { name: 'Back to Evaluation Questions' })).toHaveAttribute(
    'href',
    '/evaluation/evidence-search/questions?configuration=cfg&outcome=later_hit&page=1',
  );
  expect(screen.getByRole('link', { name: 'Next question' })).toHaveAttribute(
    'href',
    expect.stringContaining('/questions/two?'),
  );
});
