import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  Chip,
  Link,
  Paper,
  Skeleton,
  Stack,
  Typography,
} from '@mui/material';
import { useEffect, useRef, useState } from 'react';
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom';
import { errorMessage, getJson } from '../api';
import { AppShell } from '../components/AppShell';
import { EvidenceReview } from '../components/Evidence';
import {
  casePage,
  detailPath,
  filterCases,
  overviewPath,
  readEvaluationQuery,
} from '../evaluation';
import { labels, type Cases, type Summary } from '../types';
export function QuestionEvidence() {
  const { configurationId = '', questionId = '' } = useParams();
  const [params] = useSearchParams();
  const [cases, setCases] = useState<Cases | null>(null),
    [error, setError] = useState('');
  const heading = useRef<HTMLHeadingElement>(null);
  const query = readEvaluationQuery(params);
  useEffect(() => {
    setCases(null);
    setError('');
    getJson<Summary>('/api/retrieval-evaluations/current')
      .then((summary) => {
        if (!summary.configurations.some((c) => c.id === configurationId))
          throw new Error('This evaluation configuration is unavailable.');
        return getJson<Cases>(
          `/api/retrieval-evaluations/current/configurations/${configurationId}/cases`,
        );
      })
      .then(setCases)
      .catch((error: unknown) => setError(errorMessage(error)));
  }, [configurationId]);
  const item = cases?.cases.find((c) => c.id === questionId);
  useEffect(() => {
    if (item) {
      document.title = `${item.question} · Evaluation evidence`;
      heading.current?.focus();
    } else document.title = 'Question evidence · SEC Filing RAG';
    return () => {
      document.title = 'SEC Filing RAG';
    };
  }, [item]);
  const back = overviewPath(params);
  if (error)
    return (
      <AppShell maxWidth="lg">
        <Alert severity="error">
          <Typography variant="h5">Question evidence unavailable</Typography>
          <Typography>{error}</Typography>
          <Button component={RouterLink} to={back}>
            Back to evaluation overview
          </Button>
        </Alert>
      </AppShell>
    );
  if (!cases)
    return (
      <AppShell maxWidth="lg">
        <Stack aria-busy="true" spacing={2}>
          <Skeleton height={80} />
          <Skeleton variant="rounded" height={520} />
        </Stack>
      </AppShell>
    );
  if (!item)
    return (
      <AppShell maxWidth="lg">
        <Alert severity="warning">
          <Typography variant="h5">Question not found</Typography>
          <Typography>This question is not available in the selected configuration.</Typography>
          <Button component={RouterLink} to={back}>
            Back to evaluation overview
          </Button>
        </Alert>
      </AppShell>
    );
  const filtered = filterCases(cases.cases, query);
  const index = filtered.findIndex((c) => c.id === item.id);
  const previous = index > 0 ? filtered[index - 1] : null,
    next = index >= 0 && index < filtered.length - 1 ? filtered[index + 1] : null;
  const adjacent = (target: typeof item) =>
    detailPath(configurationId, target.id, params, casePage(cases, target.id, query));
  return (
    <AppShell>
      <Stack spacing={3}>
        <Breadcrumbs aria-label="Breadcrumb">
          <Link component={RouterLink} to="/evaluation" underline="hover">
            Evaluation
          </Link>
          <Typography color="text.primary">Question evidence</Typography>
        </Breadcrumbs>
        <Button
          component={RouterLink}
          to={back}
          startIcon={<ArrowBackIcon />}
          sx={{ alignSelf: 'flex-start' }}
        >
          Back to questions
        </Button>
        <Paper sx={{ p: { xs: 2, md: 3 } }}>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            sx={{ gap: 2, alignItems: { sm: 'flex-start' } }}
          >
            <Chip
              color={
                item.outcome === 'miss'
                  ? 'error'
                  : item.outcome === 'later_hit'
                    ? 'warning'
                    : 'success'
              }
              label={labels[item.outcome]}
            />
            <Box>
              <Typography component="h1" variant="h2" ref={heading} tabIndex={-1}>
                {item.question}
              </Typography>
              <Typography color="text.secondary">
                {item.ticker} · Item {item.items.join(', ')} · {item.goal.replaceAll('_', ' ')} ·{' '}
                {item.query_type.replaceAll('_', ' ')}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Configuration {configurationId}
              </Typography>
            </Box>
          </Stack>
        </Paper>
        <EvidenceReview item={item} />
        <Stack direction="row" sx={{ justifyContent: 'space-between', gap: 2 }}>
          <Button
            disabled={!previous}
            component={previous ? RouterLink : 'button'}
            to={previous ? adjacent(previous) : undefined}
            startIcon={<ChevronLeftIcon />}
          >
            Previous question
          </Button>
          <Button
            disabled={!next}
            component={next ? RouterLink : 'button'}
            to={next ? adjacent(next) : undefined}
            endIcon={<ChevronRightIcon />}
          >
            Next question
          </Button>
        </Stack>
      </Stack>
    </AppShell>
  );
}
