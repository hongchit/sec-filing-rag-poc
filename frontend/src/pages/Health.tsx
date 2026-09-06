import { Alert, Paper, Stack, Typography } from '@mui/material';
import { useEffect, useState } from 'react';
import { AppShell } from '../components/AppShell';
export function Health() {
  const [status, setStatus] = useState<'checking' | 'ready' | 'unavailable'>('checking');
  useEffect(() => {
    fetch('/api/health')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error('Health check failed'))))
      .then(() => setStatus('ready'))
      .catch(() => setStatus('unavailable'));
  }, []);
  return (
    <AppShell maxWidth="lg">
      <Paper sx={{ p: { xs: 3, md: 6 } }}>
        <Stack spacing={2}>
          <Typography variant="overline" color="primary">
            SEC Filing RAG
          </Typography>
          <Typography variant="h1">Ingestion and retrieval foundation</Typography>
          <Typography color="text.secondary">
            A Library of versioned current and historical 10-K filings with traceable SEC
            provenance.
          </Typography>
          <Alert
            severity={status === 'unavailable' ? 'error' : status === 'ready' ? 'success' : 'info'}
            aria-live="polite"
          >
            {status === 'checking'
              ? 'Checking API…'
              : status === 'ready'
                ? 'API and database ready'
                : 'API unavailable'}
          </Alert>
        </Stack>
      </Paper>
    </AppShell>
  );
}
