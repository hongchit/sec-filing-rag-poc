import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, vi, test, expect } from 'vitest';
import { ThemeProvider } from '@mui/material/styles';
import { App } from './App';
import { theme } from './theme';
import { Help } from './components/Help';

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

test('renders health shell', () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => new Promise(() => {})),
  );
  renderApp();
  expect(
    screen.getByRole('heading', { name: 'Ingestion and retrieval foundation' }),
  ).toBeInTheDocument();
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
