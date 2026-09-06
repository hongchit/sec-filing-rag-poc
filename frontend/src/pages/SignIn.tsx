import ArrowBack from '@mui/icons-material/ArrowBack';
import Login from '@mui/icons-material/Login';
import {
  Button,
  Card,
  CardContent,
  CircularProgress,
  Container,
  Stack,
  Typography,
} from '@mui/material';
import { Link as RouterLink, Navigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../authState';
import { PublicLayout } from '../components/PublicLayout';
import { safeLocalReturnTo } from '../returnTo';

function destinationDetails(path: string): { name: string; back: string; backLabel: string } {
  if (path.startsWith('/evaluation/evidence-search'))
    return {
      name: 'Evaluation Questions',
      back: '/evaluation/evidence-search',
      backLabel: 'Back to Retrieval evaluation',
    };
  if (path.startsWith('/evaluation/answer-quality'))
    return {
      name: 'RAG Answer Comparison',
      back: '/evaluation/answer-quality',
      backLabel: 'Back to RAG evaluation',
    };
  if (path.startsWith('/corpus')) return { name: 'Library', back: '/', backLabel: 'Back to home' };
  if (path.startsWith('/admin'))
    return { name: 'Administration', back: '/', backLabel: 'Back to home' };
  return { name: 'Query', back: '/', backLabel: 'Back to home' };
}

export function SignIn() {
  const [params] = useSearchParams();
  const auth = useAuth();
  const returnTo = safeLocalReturnTo(params.get('return_to'));
  const destination = destinationDetails(returnTo);
  const login = `/api/auth/google/login?policy_acknowledged=true&return_to=${encodeURIComponent(returnTo)}`;

  if (auth.status === 'loading')
    return <CircularProgress aria-label="Checking authentication" sx={{ m: 4 }} />;
  if (auth.status === 'authenticated') return <Navigate to={returnTo} replace />;

  return (
    <PublicLayout signIn={false}>
      <Container component="main" maxWidth="sm" sx={{ py: { xs: 6, md: 10 }, flex: 1 }}>
        <Card>
          <CardContent sx={{ p: { xs: 3, md: 5 } }}>
            <Stack spacing={3}>
              <Typography variant="overline" color="primary">
                {destination.name}
              </Typography>
              <Typography component="h1" variant="h1">
                Sign in required
              </Typography>
              <Typography color="text.secondary">
                Sign in to continue to {destination.name}. Saved queries, filing documents, and
                detailed evaluation records are available only to authenticated users.
              </Typography>
              <Button variant="contained" size="large" href={login} startIcon={<Login />}>
                Continue with Google
              </Button>
              <Button
                component={RouterLink}
                to={destination.back}
                startIcon={<ArrowBack />}
                sx={{ alignSelf: 'flex-start' }}
              >
                {destination.backLabel}
              </Button>
            </Stack>
          </CardContent>
        </Card>
      </Container>
    </PublicLayout>
  );
}
