import { afterEach, beforeEach, describe, expect, test } from 'vitest';
import {
  analyticsConfig,
  disableAnalytics,
  enableAnalytics,
  initializeOutboundClickTracking,
  normalizedLocation,
  normalizedReferrer,
  trackProductEvent,
} from './analytics';

function configure(value: string): void {
  document.head.innerHTML = `<meta name="sec-rag-analytics" content="${value}" />`;
}

describe('analytics', () => {
  beforeEach(() => {
    window.dataLayer = undefined;
    window.gtag = undefined;
    history.replaceState(null, '', '/research/private-id?question=secret');
    configure('');
  });

  afterEach(() => {
    disableAnalytics();
    document.head.innerHTML = '';
  });

  test('reads only supported analytics identifiers from the initial HTML', () => {
    expect(analyticsConfig()).toEqual({ kind: 'disabled', reason: 'missing' });
    configure('ga4:G-TEST123456');
    expect(analyticsConfig()).toEqual({ kind: 'ga4', id: 'G-TEST123456' });
    configure('gtm:GTM-TEST123');
    expect(analyticsConfig()).toEqual({ kind: 'gtm', id: 'GTM-TEST123' });
    configure('ga4:not-valid');
    expect(analyticsConfig()).toEqual({ kind: 'disabled', reason: 'ambiguous' });
  });

  test('normalizes page locations and removes referrer paths and query strings', () => {
    expect(normalizedLocation('/research/private-id')).toBe(
      `${window.location.origin}/research/:researchId`,
    );
    expect(normalizedReferrer(`${window.location.origin}/corpus/AAPL/1?chunk=private`)).toBe(
      `${window.location.origin}/corpus/:ticker/:item`,
    );
    expect(normalizedReferrer('https://search.example/path?q=private')).toBe(
      'https://search.example/',
    );
    expect(normalizedReferrer('not a URL')).toBe('');
  });

  test('loads GA4 and emits only allowlisted event data after enablement', () => {
    configure('ga4:G-TEST123456');

    enableAnalytics();
    trackProductEvent({ name: 'research_completed', outcome: 'answered' });

    expect(document.querySelector<HTMLScriptElement>('#sec-research-ga4')?.src).toBe(
      'https://www.googletagmanager.com/gtag/js?id=G-TEST123456',
    );
    const queued = window.dataLayer ?? [];
    expect(queued.slice(0, 4).every((entry) => !Array.isArray(entry))).toBe(true);
    const calls: unknown[][] = queued.map((entry): unknown[] =>
      Array.from(entry as ArrayLike<unknown>),
    );
    expect(calls.slice(0, 4).map(([command]) => command)).toEqual([
      'consent',
      'js',
      'config',
      'event',
    ]);
    expect(calls).toContainEqual([
      'event',
      'research_completed',
      expect.objectContaining({
        outcome: 'answered',
        page_location: `${window.location.origin}/research/:researchId`,
      }),
    ]);
    expect(JSON.stringify(calls)).not.toContain('private-id');
    expect(JSON.stringify(calls)).not.toContain('question=secret');
  });

  test('does not emit events when analytics is disabled or withdrawn', () => {
    trackProductEvent({ name: 'research_started' });
    expect(window.dataLayer).toBeUndefined();

    configure('ga4:G-TEST123456');
    enableAnalytics();
    disableAnalytics();
    trackProductEvent({ name: 'research_started' });

    expect(window.dataLayer).toEqual([]);
    expect(document.querySelector('#sec-research-ga4')).toBeNull();
  });

  test('tracks outbound clicks by safe destination category without sending URLs', () => {
    configure('ga4:G-TEST123456');
    enableAnalytics();
    const stop = initializeOutboundClickTracking();
    const anchor = document.createElement('a');
    anchor.href = 'https://www.sec.gov/Archives/private-accession?token=secret';
    anchor.innerHTML = '<span>Open filing</span>';
    anchor.addEventListener('click', (event) => event.preventDefault());
    document.body.append(anchor);

    anchor
      .querySelector('span')
      ?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    stop();
    anchor.remove();

    const calls = (window.dataLayer ?? []).map((entry): unknown[] =>
      Array.from(entry as ArrayLike<unknown>),
    );
    expect(calls).toContainEqual([
      'event',
      'outbound_link_clicked',
      expect.objectContaining({ destination: 'sec_edgar' }),
    ]);
    expect(JSON.stringify(calls)).not.toContain('private-accession');
    expect(JSON.stringify(calls)).not.toContain('token=secret');
  });

  test('ignores same-origin links', () => {
    configure('ga4:G-TEST123456');
    enableAnalytics();
    const initialCount = window.dataLayer?.length ?? 0;
    const stop = initializeOutboundClickTracking();
    const anchor = document.createElement('a');
    anchor.href = '/research/history';
    anchor.addEventListener('click', (event) => event.preventDefault());
    document.body.append(anchor);

    anchor.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    stop();
    anchor.remove();

    expect(window.dataLayer).toHaveLength(initialCount);
  });
});
