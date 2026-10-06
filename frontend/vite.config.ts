import react from '@vitejs/plugin-react';
import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', 'VITE_');
  const mechanisms = [env.VITE_GTM_CONTAINER_ID, env.VITE_GA4_MEASUREMENT_ID].filter(Boolean);
  const analyticsMeta = env.VITE_GTM_CONTAINER_ID
    ? /^GTM-[A-Z0-9]+$/.test(env.VITE_GTM_CONTAINER_ID)
      ? `gtm:${env.VITE_GTM_CONTAINER_ID}`
      : ''
    : env.VITE_GA4_MEASUREMENT_ID && /^G-[A-Z0-9]+$/.test(env.VITE_GA4_MEASUREMENT_ID)
      ? `ga4:${env.VITE_GA4_MEASUREMENT_ID}`
      : '';
  if (mechanisms.length !== 1 || !analyticsMeta)
    console.warn(
      mechanisms.length === 0
        ? 'Analytics disabled: configure exactly one of VITE_GTM_CONTAINER_ID or VITE_GA4_MEASUREMENT_ID.'
        : mechanisms.length > 1
          ? 'Analytics disabled: both VITE_GTM_CONTAINER_ID and VITE_GA4_MEASUREMENT_ID are configured.'
          : 'Analytics disabled: the configured identifier is malformed.',
    );
  return {
    envDir: '..',
    plugins: [
      react(),
      {
        name: 'runtime-analytics-meta',
        transformIndexHtml(html) {
          return mechanisms.length === 1 && analyticsMeta
            ? html.replace(
                '<meta name="sec-rag-analytics" content="" />',
                `<meta name="sec-rag-analytics" content="${analyticsMeta}" />`,
              )
            : html;
        },
      },
    ],
    server: { proxy: { '/api': 'http://localhost:8000' } },
    test: { environment: 'jsdom', server: { deps: { inline: [/@mui\/x-data-grid/] } } },
  };
});
