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

const gtmId = import.meta.env.VITE_GTM_CONTAINER_ID?.trim();
const ga4Id = import.meta.env.VITE_GA4_MEASUREMENT_ID?.trim();

export const analyticsConfig: AnalyticsConfig =
  gtmId && ga4Id
    ? { kind: 'disabled', reason: 'ambiguous' }
    : gtmId
      ? { kind: 'gtm', id: gtmId }
      : ga4Id
        ? { kind: 'ga4', id: ga4Id }
        : { kind: 'disabled', reason: 'missing' };

let loaded = false;

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

export function enableAnalytics(): void {
  if (loaded || analyticsConfig.kind === 'disabled') return;
  loaded = true;
  window.dataLayer = window.dataLayer ?? [];
  window.gtag = (...args: unknown[]) => window.dataLayer?.push(args);
  window.gtag('consent', 'update', {
    analytics_storage: 'granted',
    ad_storage: 'denied',
    ad_user_data: 'denied',
    ad_personalization: 'denied',
  });
  if (analyticsConfig.kind === 'gtm') {
    window.dataLayer.push({ 'gtm.start': Date.now(), event: 'gtm.js' });
    script(
      `https://www.googletagmanager.com/gtm.js?id=${encodeURIComponent(analyticsConfig.id)}`,
      'sec-research-gtm',
    );
  } else {
    script(
      `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(analyticsConfig.id)}`,
      'sec-research-ga4',
    );
    window.gtag('js', new Date());
    window.gtag('config', analyticsConfig.id, {
      send_page_view: false,
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
      restricted_data_processing: true,
    });
  }
  trackPageView();
}

export function disableAnalytics(): boolean {
  const wasLoaded = loaded;
  if (window.gtag) window.gtag('consent', 'update', { analytics_storage: 'denied' });
  if (analyticsConfig.kind === 'ga4')
    Object.assign(window, { [`ga-disable-${analyticsConfig.id}`]: true });
  document.querySelectorAll('script[data-analytics="true"]').forEach((node) => node.remove());
  window.dataLayer = [];
  window.gtag = undefined;
  loaded = false;
  return wasLoaded;
}

export function trackPageView(): void {
  if (!loaded || !window.gtag) return;
  window.gtag('event', 'page_view', {
    page_path: normalizedRoute(),
    page_location: undefined,
    user_id: undefined,
  });
}
