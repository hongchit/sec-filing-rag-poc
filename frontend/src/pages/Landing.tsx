import ArrowForward from '@mui/icons-material/ArrowForward';
import FactCheckOutlined from '@mui/icons-material/FactCheckOutlined';
import Login from '@mui/icons-material/Login';
import ManageSearch from '@mui/icons-material/ManageSearch';
import QuestionAnswerOutlined from '@mui/icons-material/QuestionAnswerOutlined';
import { Box, Button, Card, Container, Grid, Link, Stack, Typography } from '@mui/material';
import { Link as RouterLink, useLocation } from 'react-router-dom';
import { PublicLayout } from '../components/PublicLayout';

export function Landing() {
  const location = useLocation();
  const returnTo =
    location.pathname === '/' ? '/research' : `${location.pathname}${location.search}`;
  const login = `/api/auth/google/login?policy_acknowledged=true&return_to=${encodeURIComponent(returnTo)}`;
  return (
    <PublicLayout>
      <Container component="main" maxWidth="lg" sx={{ py: { xs: 5, md: 8 }, flex: 1 }}>
        <Grid container spacing={{ xs: 5, md: 8 }} alignItems="center">
          <Grid size={{ xs: 12, md: 7 }}>
            <Stack spacing={3}>
              <Typography
                color="primary"
                fontWeight={750}
                letterSpacing=".08em"
                textTransform="uppercase"
              >
                Evidence-first company research
              </Typography>
              <Typography component="h1" variant="h1">
                Understand annual filings without reading every page.
              </Typography>
              <Typography variant="h6" color="text.secondary" fontWeight={400} maxWidth={690}>
                Ask a plain-language question. SEC Filing Research finds relevant passages in annual
                filings, drafts a focused answer, and keeps every claim connected to its source.
              </Typography>
              <Box>
                <Button
                  variant="contained"
                  size="large"
                  href={login}
                  startIcon={<Login />}
                  endIcon={<ArrowForward />}
                >
                  Sign in with Google
                </Button>
              </Box>
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
              <Typography variant="body2" color="text.secondary">
                This site uses cookies and similar technologies to operate securely and, with your
                permission, understand how it is used. You can manage optional cookies at any time.
              </Typography>
            </Stack>
          </Grid>
          <Grid size={{ xs: 12, md: 5 }}>
            <Card sx={{ p: 3, bgcolor: '#eef4f1' }}>
              <Stack spacing={2}>
                <Typography variant="overline">Example research</Typography>
                <Typography fontWeight={700}>Question</Typography>
                <Typography>What risks could affect the company’s supply chain?</Typography>
                <Typography fontWeight={700}>Answer</Typography>
                <Typography color="text.secondary">
                  The filing identifies supplier concentration and component availability as
                  material risks…
                </Typography>
                <Typography variant="caption" color="primary" fontWeight={700}>
                  Source · Form 10-K, Item 1A · View passage
                </Typography>
              </Stack>
            </Card>
          </Grid>
        </Grid>
        <Grid container spacing={2} sx={{ mt: { xs: 5, md: 8 } }}>
          {[
            [
              <QuestionAnswerOutlined key="q" />,
              '1. Ask',
              'Choose a company and ask a focused question.',
            ],
            [
              <ManageSearch key="s" />,
              '2. Find evidence',
              'Measured retrieval selects relevant filing passages.',
            ],
            [
              <FactCheckOutlined key="v" />,
              '3. Verify',
              'Read the answer, then inspect its cited sources.',
            ],
          ].map(([icon, title, body], index) => (
            <Grid size={{ xs: 12, md: 4 }} key={index}>
              <Stack direction="row" spacing={2} sx={{ p: 2 }}>
                <Box color="primary.main">{icon}</Box>
                <Box>
                  <Typography fontWeight={750}>{title}</Typography>
                  <Typography color="text.secondary">{body}</Typography>
                </Box>
              </Stack>
            </Grid>
          ))}
        </Grid>
        <Typography textAlign="center" color="text.secondary" sx={{ mt: 4 }}>
          Answers are grounded in source filings and should be verified. This service is for
          research and is not investment advice.
        </Typography>
      </Container>
    </PublicLayout>
  );
}
