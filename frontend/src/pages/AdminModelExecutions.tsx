import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Button,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useCallback, useEffect, useState } from 'react';
import { AdminError } from './Admin';

type ModelOperation = {
  operation: string;
  model: string;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  usage_status: string;
  normalized_status: string;
  retry_count: number;
};
type ModelExecution = {
  run_type: string;
  id: string;
  status: string;
  safe_error?: string | null;
  started_at: string;
  finished_at?: string | null;
  models: string[];
  operations: ModelOperation[];
  provider_calls: number;
  retries: number;
  failures: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  usage_available: boolean;
  estimated_usd?: string | null;
  pricing_basis: 'stored_snapshot' | 'current_price_estimate';
};

export function AdminModelExecutions() {
  const [executions, setExecutions] = useState<ModelExecution[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async (offset = 0) => {
    setLoading(true);
    setError('');
    const response = await fetch(`/api/admin/model-executions?limit=25&offset=${offset}`);
    setLoading(false);
    if (!response.ok) {
      setError(
        response.status === 403
          ? 'Administrator access is required.'
          : 'Operational model executions could not be loaded.',
      );
      return;
    }
    const value = (await response.json()) as {
      items: ModelExecution[];
      next_offset: number | null;
    };
    const items = Array.isArray(value.items) ? value.items : [];
    setExecutions((current) => (offset === 0 ? items : [...current, ...items]));
    setNextOffset(value.next_offset ?? null);
  }, []);
  useEffect(() => void load(), [load]);
  return (
    <Stack spacing={3}>
      <Stack spacing={0.5}>
        <Typography variant="h2">Operational model executions</Typography>
        <Typography color="text.secondary">
          Evaluation and ground-truth costs are operational estimates and do not affect user
          allowances.
        </Typography>
      </Stack>
      {error && <AdminError message={error} />}
      {loading && executions.length === 0 && <Typography>Loading model executions…</Typography>}
      {!loading && !error && executions.length === 0 && (
        <Typography>No operational executions recorded.</Typography>
      )}
      {executions.map((execution) => (
        <Accordion key={`${execution.run_type}:${execution.id}`}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Stack spacing={0.25}>
              <Typography>
                {execution.run_type.replaceAll('_', ' ')} · {execution.status} ·{' '}
                {execution.estimated_usd === null
                  ? 'cost unavailable'
                  : `$${Number(execution.estimated_usd).toFixed(6)}`}
              </Typography>
              <Typography variant="caption">
                {execution.provider_calls} calls · {execution.retries} retries ·{' '}
                {execution.failures} failures · {execution.total_tokens} tokens ·{' '}
                {execution.pricing_basis === 'current_price_estimate'
                  ? 'current-price estimate'
                  : 'stored pricing snapshot'}
              </Typography>
            </Stack>
          </AccordionSummary>
          <AccordionDetails>
            <Stack spacing={1}>
              <Typography variant="caption">Run ID: {execution.id}</Typography>
              <Typography variant="caption">
                Started: {execution.started_at} · Finished: {execution.finished_at ?? 'running'}
              </Typography>
              <Typography variant="caption">
                Models: {execution.models.join(', ') || 'none'} · Input tokens:{' '}
                {execution.input_tokens} · Output tokens: {execution.output_tokens} · Usage:{' '}
                {execution.usage_available ? 'available' : 'unavailable'}
              </Typography>
              {execution.safe_error && <Alert severity="error">{execution.safe_error}</Alert>}
              {execution.operations.map((operation, index) => (
                <Paper key={`${operation.operation}:${index}`} variant="outlined" sx={{ p: 1.5 }}>
                  <Typography>
                    {operation.operation} · {operation.model} · {operation.usage_status}
                  </Typography>
                  <Typography variant="caption">
                    Input {operation.input_tokens ?? 'unavailable'} · Output{' '}
                    {operation.output_tokens ?? 'unavailable'} · Total{' '}
                    {operation.total_tokens ?? 'unavailable'} · Retries {operation.retry_count}
                  </Typography>
                  {operation.normalized_status !== 'succeeded' && (
                    <Typography color="error">{operation.normalized_status}</Typography>
                  )}
                </Paper>
              ))}
            </Stack>
          </AccordionDetails>
        </Accordion>
      ))}
      {nextOffset !== null && (
        <Button disabled={loading} onClick={() => void load(nextOffset)}>
          {loading ? 'Loading…' : 'Load more'}
        </Button>
      )}
    </Stack>
  );
}
