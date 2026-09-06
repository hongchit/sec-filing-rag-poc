import ArrowBack from '@mui/icons-material/ArrowBack';
import ArrowForward from '@mui/icons-material/ArrowForward';
import FactCheckOutlined from '@mui/icons-material/FactCheckOutlined';
import Login from '@mui/icons-material/Login';
import ManageSearch from '@mui/icons-material/ManageSearch';
import QuestionAnswerOutlined from '@mui/icons-material/QuestionAnswerOutlined';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Container,
  Grid,
  IconButton,
  Link,
  MobileStepper,
  Stack,
  Typography,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { Link as RouterLink, useLocation } from 'react-router-dom';
import { getJson } from '../api';
import { OptionalAuth } from '../auth';
import { AppShell } from '../components/AppShell';
import { PublicLayout } from '../components/PublicLayout';
import { researchPath } from '../evaluation';
import { safeLocalReturnTo } from '../returnTo';

type ShowcaseExample = {
  id: string;
  question: string;
  answer: string;
  ticker: string;
  filing_period: string;
  accession: string;
  items: string[];
  citations: string[];
  goal: string;
};
const itemNames: Record<string, string> = {
  '1': 'Business',
  '1A': 'Risk Factors',
  '3': 'Legal Proceedings',
  '7': "Management's Discussion and Analysis",
  '7A': 'Market Risk',
  '8': 'Financial Statements',
};

function LandingContent({ authenticated }: { authenticated: boolean }) {
  const location = useLocation();
  const [examples, setExamples] = useState<ShowcaseExample[]>([]);
  const [active, setActive] = useState(0);
  useEffect(() => {
    void getJson<{ examples: ShowcaseExample[] }>('/api/showcase')
      .then((value) => setExamples(value.examples))
      .catch(() => setExamples([]));
  }, [authenticated]);
  const returnTo = safeLocalReturnTo(new URLSearchParams(location.search).get('return_to'));
  const login = `/api/auth/google/login?policy_acknowledged=true&return_to=${encodeURIComponent(returnTo)}`;
  const example = examples[active];
  const exampleResearch = example ? researchPath(example) : '';
  const exampleLogin = `/api/auth/google/login?policy_acknowledged=true&return_to=${encodeURIComponent(exampleResearch)}`;
  const content = (
    <Stack spacing={{ xs: 5, md: 8 }}>
      <Grid container spacing={{ xs: 4, md: 7 }} alignItems="center">
        <Grid size={{ xs: 12, md: examples.length ? 7 : 12 }}>
          <Stack spacing={3} maxWidth={760}>
            <Typography variant="overline" color="primary">
              RAG demo using SEC Form 10-K filings
            </Typography>
            <Typography component="h1" variant="h1">
              Ask an annual report a question. Get a cited answer.
            </Typography>
            <Typography variant="h6" color="text.secondary" fontWeight={400}>
              Retrieval-augmented generation finds relevant passages in a company filing and passes
              them to a Large-Language Model (LLM) when you ask. The answer remains connected to
              evidence you can inspect.
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} gap={1.5} alignItems={{ sm: 'center' }}>
              {authenticated ? (
                <Button
                  variant="contained"
                  size="large"
                  component={RouterLink}
                  to="/research"
                  endIcon={<ArrowForward />}
                >
                  Open Query
                </Button>
              ) : (
                <Button
                  variant="contained"
                  size="large"
                  href={login}
                  startIcon={<Login />}
                  endIcon={<ArrowForward />}
                >
                  Sign in to try Query
                </Button>
              )}
              <Button variant="outlined" size="large" component={RouterLink} to="/overview">
                Why use RAG?
              </Button>
            </Stack>
            {!authenticated && (
              <Typography variant="body2" color="text.secondary">
                By signing in, you agree to the{' '}
                <Link component={RouterLink} to="/terms">
                  Terms of Service
                </Link>{' '}
                and acknowledge the{' '}
                <Link component={RouterLink} to="/privacy">
                  Privacy Policy
                </Link>
                .
              </Typography>
            )}
          </Stack>
        </Grid>
        {example && (
          <Grid size={{ xs: 12, md: 5 }}>
            <Card sx={{ bgcolor: '#eef4f1' }} aria-live="polite">
              <CardContent>
                <Stack spacing={2}>
                  <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Typography variant="overline" color="primary">
                      Curated example
                    </Typography>
                    <Typography variant="caption">
                      Example {active + 1} of {examples.length}
                    </Typography>
                  </Stack>
                  <Typography variant="h3">{example.question}</Typography>
                  <Typography>{example.answer}</Typography>
                  <Stack direction="row" gap={0.75} flexWrap="wrap">
                    <Chip label={example.ticker} />
                    <Chip label={`Form 10-K · ${example.filing_period}`} />
                    {example.items.map((item) => (
                      <Chip
                        key={item}
                        label={`Item ${item} · ${itemNames[item] || 'Filing section'}`}
                      />
                    ))}
                  </Stack>
                  <Stack direction="row" gap={0.75} flexWrap="wrap" aria-label="Citation handles">
                    {example.citations.map((citation) => (
                      <Chip
                        key={citation}
                        variant="outlined"
                        label={citation}
                        sx={{ maxWidth: '100%' }}
                      />
                    ))}
                  </Stack>
                  <Button
                    variant="contained"
                    component={authenticated ? RouterLink : 'a'}
                    to={authenticated ? exampleResearch : undefined}
                    href={authenticated ? undefined : exampleLogin}
                    endIcon={<ArrowForward />}
                  >
                    Try this question in Query
                  </Button>
                </Stack>
              </CardContent>
              {examples.length > 1 && (
                <MobileStepper
                  variant="dots"
                  steps={examples.length}
                  position="static"
                  activeStep={active}
                  nextButton={
                    <IconButton
                      aria-label="Next example"
                      onClick={() => setActive((value) => Math.min(value + 1, examples.length - 1))}
                      disabled={active === examples.length - 1}
                    >
                      <ArrowForward />
                    </IconButton>
                  }
                  backButton={
                    <IconButton
                      aria-label="Previous example"
                      onClick={() => setActive((value) => Math.max(value - 1, 0))}
                      disabled={active === 0}
                    >
                      <ArrowBack />
                    </IconButton>
                  }
                />
              )}
            </Card>
          </Grid>
        )}
      </Grid>
      <Grid container spacing={2}>
        {[
          ['What this is', 'A working RAG system over configured public Form 10-K filings.'],
          [
            'What you can do',
            'Ask focused business and risk questions, then trace answers to the filing passages.',
          ],
          [
            'Why it matters',
            'Ask questions about up-to-date filing evidence using an LLM without retraining the model.',
          ],
        ].map(([title, body]) => (
          <Grid size={{ xs: 12, md: 4 }} key={title}>
            <Card sx={{ height: '100%' }}>
              <CardContent>
                <Typography variant="h3">{title}</Typography>
                <Typography color="text.secondary" mt={1}>
                  {body}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
      <Box component="section">
        <Typography variant="overline" color="primary">
          From question to checkable answer
        </Typography>
        <Typography variant="h2" mb={2}>
          Move from a focused question to a cited answer.
        </Typography>
        <Grid container spacing={2}>
          {[
            {
              icon: <QuestionAnswerOutlined />,
              title: '1. Ask',
              body: 'Choose a company and ask a focused question.',
            },
            {
              icon: <ManageSearch />,
              title: '2. Find evidence',
              body: 'Hybrid retrieval searches the selected filing.',
            },
            {
              icon: <FactCheckOutlined />,
              title: '3. Answer',
              body: 'The model responds using the retrieved passages.',
            },
          ].map(({ icon, title, body }) => (
            <Grid size={{ xs: 12, sm: 6, lg: 4 }} key={title}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Box color="primary.main">{icon}</Box>
                  <Typography fontWeight={750} mt={1}>
                    {title}
                  </Typography>
                  <Typography color="text.secondary">{body}</Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
        <Stack direction={{ xs: 'column', sm: 'row' }} gap={1.5} mt={3}>
          <Button component={RouterLink} to="/overview">
            Understand why RAG helps
          </Button>
          <Button component={RouterLink} to="/how-it-works">
            See how the system is built
          </Button>
          <Button component={RouterLink} to="/evaluation">
            See how quality was measured
          </Button>
        </Stack>
      </Box>
      <Typography textAlign="center" color="text.secondary">
        Responses can still be incomplete or wrong. This educational proof of concept is not
        investment advice.
      </Typography>
    </Stack>
  );
  return authenticated ? (
    <AppShell maxWidth="lg">{content}</AppShell>
  ) : (
    <PublicLayout>
      <Container component="main" maxWidth="lg" sx={{ py: { xs: 5, md: 8 }, flex: 1 }}>
        {content}
      </Container>
    </PublicLayout>
  );
}

export function Landing() {
  return (
    <OptionalAuth>{(account) => <LandingContent authenticated={Boolean(account)} />}</OptionalAuth>
  );
}
