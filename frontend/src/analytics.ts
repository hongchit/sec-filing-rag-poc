type AnalyticsConfig =
  | { kind: 'gtm'; id: string }
  | { kind: 'ga4'; id: string }
  | { kind: 'disabled'; reason: 'missing' | 'ambiguous' };

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
  }
}

let loaded = false;
let activeConfig: AnalyticsConfig = { kind: 'disabled', reason: 'missing' };

export type ProductEvent =
  | { name: 'research_started' }
  | {
      name: 'research_completed';
      outcome: 'answered' | 'rejected' | 'insufficient_evidence' | 'failed';
    }
  | { name: 'research_request_error' }
  | { name: 'filing_preparation_requested'; mode: 'single' | 'latest' }
  | { name: 'feedback_submitted'; rating: 'up' | 'down' }
  | { name: 'outbound_link_clicked'; destination: 'sec_edgar' | 'github' | 'external' };

export function analyticsConfig(): AnalyticsConfig {
  const raw = document
    .querySelector<HTMLMetaElement>('meta[name="sec-rag-analytics"]')
    ?.content.trim();
  if (raw?.startsWith('gtm:') && /^GTM-[A-Z0-9]+$/.test(raw.slice(4)))
    return { kind: 'gtm', id: raw.slice(4) };
  if (raw?.startsWith('ga4:') && /^G-[A-Z0-9]+$/.test(raw.slice(4)))
    return { kind: 'ga4', id: raw.slice(4) };
  return { kind: 'disabled', reason: raw ? 'ambiguous' : 'missing' };
}

export function normalizedRoute(pathname = window.location.pathname): string {
  if (/^\/research\/[^/]+$/.test(pathname)) return '/research/:researchId';
  if (/^\/corpus\/[^/]+\/[^/]+$/.test(pathname)) return '/corpus/:ticker/:item';
  if (/^\/evaluation\/evidence-search\/configurations\/[^/]+\/questions\/[^/]+$/.test(pathname))
    return '/evaluation/evidence-search/configurations/:configurationId/questions/:questionId';
  if (/^\/evaluation\/answer-quality\/questions\/[^/]+$/.test(pathname))
    return '/evaluation/answer-quality/questions/:questionId';
  return [
    '/',
    '/research',
    '/research/history',
    '/profile',
    '/corpus',
    '/overview',
    '/how-it-works',
    '/evaluation',
    '/evaluation/evidence-search',
    '/evaluation/evidence-search/questions',
    '/evaluation/answer-quality',
    '/evaluation/answer-quality/questions',
    '/diagnostics/health',
    '/admin',
    '/admin/users',
    '/admin/model-executions',
    '/privacy',
    '/terms',
    '/sign-in',
  ].includes(pathname)
    ? pathname
    : '/other';
}

function script(src: string, id: string): void {
  if (document.getElementById(id)) return;
  const element = document.createElement('script');
  element.id = id;
  element.async = true;
  element.src = src;
  element.dataset.analytics = 'true';
  document.head.append(element);
}

export function normalizedLocation(pathname = window.location.pathname): string {
  return new URL(normalizedRoute(pathname), window.location.origin).href;
}

export function normalizedReferrer(referrer = document.referrer): string {
  if (!referrer) return '';
  try {
    const parsed = new URL(referrer);
    return parsed.origin === window.location.origin
      ? new URL(normalizedRoute(parsed.pathname), parsed.origin).href
      : `${parsed.origin}/`;
  } catch {
    return '';
  }
}

function safeContext(): Record<string, string> {
  return {
    page_location: normalizedLocation(),
    page_referrer: normalizedReferrer(),
  };
}

export function enableAnalytics(): void {
  const configured = analyticsConfig();
  if (loaded || configured.kind === 'disabled') return;
  activeConfig = configured;
  loaded = true;
  window.dataLayer = window.dataLayer ?? [];
  window.gtag = function () {
    // gtag.js distinguishes its canonical arguments queue from ordinary data-layer arrays.
    // eslint-disable-next-line prefer-rest-params
    window.dataLayer?.push(arguments);
  };
  window.gtag('consent', 'update', {
    analytics_storage: 'granted',
    ad_storage: 'denied',
    ad_user_data: 'denied',
    ad_personalization: 'denied',
  });
  if (configured.kind === 'gtm') {
    window.dataLayer.push({ 'gtm.start': Date.now(), event: 'gtm.js' });
    script(
      `https://www.googletagmanager.com/gtm.js?id=${encodeURIComponent(configured.id)}`,
      'sec-research-gtm',
    );
  } else {
    Object.assign(window, { [`ga-disable-${configured.id}`]: false });
    script(
      `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(configured.id)}`,
      'sec-research-ga4',
    );
    window.gtag('js', new Date());
    window.gtag('config', configured.id, {
      send_page_view: false,
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
      restricted_data_processing: true,
      ...safeContext(),
    });
  }
  trackPageView();
}

export function disableAnalytics(): boolean {
  const wasLoaded = loaded;
  if (window.gtag) window.gtag('consent', 'update', { analytics_storage: 'denied' });
  if (activeConfig.kind === 'ga4')
    Object.assign(window, { [`ga-disable-${activeConfig.id}`]: true });
  document.querySelectorAll('script[data-analytics="true"]').forEach((node) => node.remove());
  window.dataLayer = [];
  window.gtag = undefined;
  loaded = false;
  activeConfig = { kind: 'disabled', reason: 'missing' };
  return wasLoaded;
}

export function trackPageView(): void {
  if (!loaded || !window.gtag) return;
  window.gtag('event', 'page_view', {
    page_path: normalizedRoute(),
    ...safeContext(),
  });
}

export function trackProductEvent(event: ProductEvent): void {
  if (!loaded || !window.gtag) return;
  const { name, ...parameters } = event;
  window.gtag('event', name, { ...parameters, ...safeContext() });
}

function outboundDestination(hostname: string): 'sec_edgar' | 'github' | 'external' {
  const normalized = hostname.toLowerCase();
  if (normalized === 'sec.gov' || normalized.endsWith('.sec.gov')) return 'sec_edgar';
  if (normalized === 'github.com' || normalized.endsWith('.github.com')) return 'github';
  return 'external';
}

export function initializeOutboundClickTracking(root: Document = document): () => void {
  const listener = (event: MouseEvent) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const anchor = target.closest<HTMLAnchorElement>('a[href]');
    if (!anchor) return;
    try {
      const destination = new URL(anchor.href, window.location.href);
      if (!['http:', 'https:'].includes(destination.protocol)) return;
      if (destination.origin === window.location.origin) return;
      trackProductEvent({
        name: 'outbound_link_clicked',
        destination: outboundDestination(destination.hostname),
      });
    } catch {
      return;
    }
  };
  root.addEventListener('click', listener, { capture: true });
  return () => root.removeEventListener('click', listener, { capture: true });
}
