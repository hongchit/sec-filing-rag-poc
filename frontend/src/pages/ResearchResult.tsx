import {
  Alert,
  Box,
  Button,
  Chip,
  Collapse,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import type { Research } from '../researchTypes';

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export function ResearchResult() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [value, setValue] = useState<Research>();
  const [error, setError] = useState('');
  const [details, setDetails] = useState(false);
  const [rating, setRating] = useState<'up' | 'down'>();
  const [comment, setComment] = useState('');
  const refs = useRef<Record<string, HTMLDivElement | null>>({});
  useEffect(() => {
    if (!uuid.test(id)) {
      setError('Invalid research ID.');
      return;
    }
    void fetch(`/api/research/${id}`)
      .then((r) => {
        if (!r.ok) throw new Error('Research not found.');
        return r.json();
      })
      .then((body: unknown) => setValue(body as Research))
      .catch((error: unknown) =>
        setError(error instanceof Error ? error.message : 'Research unavailable.'),
      );
  }, [id]);
  function cite(handle: string) {
    const node = refs.current[handle];
    node?.scrollIntoView({
      behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    });
    node?.focus();
  }
  async function save() {
    await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ result_type: 'research_answer', result_id: id, rating, comment }),
    });
  }
  if (error)
    return (
      <AppShell>
        <Alert severity="error">{error}</Alert>
      </AppShell>
    );
  if (!value)
    return (
      <AppShell>
        <Alert severity="info" aria-live="polite">
          Loading research…
        </Alert>
      </AppShell>
    );
  if (value.status === 'failed')
    return (
      <AppShell>
        <Stack spacing={2}>
          <Typography variant="h1">Research could not be completed</Typography>
          <Alert severity="error">{value.safe_error ?? 'A provider operation failed.'}</Alert>
          <Typography>{value.question}</Typography>
          <Typography>ID: {value.research_id}</Typography>
          <Button
            variant="contained"
            onClick={() => void navigate('/research', { state: { retry: value } })}
          >
            Retry as new research
          </Button>
        </Stack>
      </AppShell>
    );
  const usage = value.usage;
  const rejected =
    value.disposition === 'investment_advice' || value.disposition === 'out_of_scope';
  const charge = value.estimated_charge_usd
    ? Number(value.estimated_charge_usd).toLocaleString('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 6,
      })
    : 'unavailable';
  return (
    <AppShell>
      <Stack spacing={3}>
        <Box>
          <Typography variant="overline">
            {value.ticker} · {value.run_details.accession as string}
          </Typography>
          <Typography variant="h1">{value.question}</Typography>
        </Box>
        {rejected && <Alert severity="warning">{value.rejection_message}</Alert>}
        {!rejected && value.insufficient_evidence && (
          <Alert severity="warning">
            The retrieved filing evidence is insufficient for a complete answer.
          </Alert>
        )}
        {!rejected &&
          value.limitations?.map((item) => (
            <Alert key={item} severity="info">
              {item}
            </Alert>
          ))}
        {!rejected && (
          <Stack spacing={2}>
            {value.answer?.map((paragraph, index) => (
              <Paper key={index} sx={{ p: 3 }}>
                <Chip
                  size="small"
                  label={paragraph.kind === 'filing_fact' ? 'Filing fact' : 'Interpretation'}
                />
                <Typography sx={{ my: 1 }}>{paragraph.text}</Typography>
                {paragraph.citations.map((handle) => (
                  <Button key={handle} size="small" onClick={() => cite(handle)}>
                    {handle}
                  </Button>
                ))}
              </Paper>
            ))}
          </Stack>
        )}
        <Typography variant="body2">
          Token usage: embedding {usage.query_embedding_input ?? 'unavailable'} · answer in{' '}
          {usage.answer_generation_input ?? 'unavailable'} · answer out{' '}
          {usage.answer_generation_output ?? 'unavailable'} · total{' '}
          <strong>{usage.complete_request_total ?? 'unavailable'}</strong>
        </Typography>
        <Typography variant="body2">
          Estimated charge: <strong>{charge}</strong>
        </Typography>
        {!rejected && (
          <Box>
            <Typography variant="h2">Sources</Typography>
            {value.evidence.map((source) => (
              <Paper
                key={source.chunk_id}
                ref={(node) => {
                  refs.current[source.citation_handle] = node;
                }}
                tabIndex={-1}
                sx={{ p: 2, mt: 1 }}
              >
                <Typography variant="subtitle2">
                  #{source.rank} · Item {source.item} · {source.citation_handle}
                </Typography>
                <Typography>{source.excerpt}</Typography>
                <Button component="a" href={source.source_url} target="_blank" rel="noreferrer">
                  View on EDGAR
                </Button>
                <Button
                  component={Link}
                  to={`/corpus/${source.ticker}/${source.item}?corpus=${source.corpus_version_id || value.corpus_version_id}&chunk=${source.chunk_id}`}
                  state={{
                    origin: { to: `/research/${value.research_id}`, label: 'Research result' },
                  }}
                >
                  Read in context
                </Button>
              </Paper>
            ))}
          </Box>
        )}
        <Box>
          <Button onClick={() => setDetails((v) => !v)} aria-expanded={details}>
            Run details
          </Button>
          <Collapse in={details}>
            <Paper sx={{ p: 2 }}>
              <Typography>
                <Link to="/evaluation">Weighted hybrid, α=0.25 — selected by MRR</Link>
              </Typography>
              <pre style={{ whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(value.run_details, null, 2)}
              </pre>
            </Paper>
          </Collapse>
        </Box>
        <Box>
          <Typography>Was this useful?</Typography>
          <Button onClick={() => setRating('up')} aria-pressed={rating === 'up'}>
            👍
          </Button>
          <Button onClick={() => setRating('down')} aria-pressed={rating === 'down'}>
            👎
          </Button>
          {rating && (
            <Stack spacing={1}>
              <TextField
                label="Optional comment"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                inputProps={{ maxLength: 1000 }}
              />
              <Button onClick={() => void save()}>Save feedback</Button>
            </Stack>
          )}
        </Box>
      </Stack>
    </AppShell>
  );
}
