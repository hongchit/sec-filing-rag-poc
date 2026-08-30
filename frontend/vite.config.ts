import react from '@vitejs/plugin-react';
import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', 'VITE_');
  const mechanisms = [env.VITE_GTM_CONTAINER_ID, env.VITE_GA4_MEASUREMENT_ID].filter(Boolean);
  if (mechanisms.length !== 1)
    console.warn(
      mechanisms.length === 0
        ? 'Analytics disabled: configure exactly one of VITE_GTM_CONTAINER_ID or VITE_GA4_MEASUREMENT_ID.'
        : 'Analytics disabled: both VITE_GTM_CONTAINER_ID and VITE_GA4_MEASUREMENT_ID are configured.',
    );
  return {
    envDir: '..',
    plugins: [react()],
    server: { proxy: { '/api': 'http://localhost:8000' } },
    test: { environment: 'jsdom', server: { deps: { inline: [/@mui\/x-data-grid/] } } },
  };
});
