import CookieOutlined from '@mui/icons-material/CookieOutlined';
import { Box, Button, Container, Link, Stack, Typography } from '@mui/material';
import type { ReactNode } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { showCookiePreferences } from '../consent';

export function Brand({ destination = '/' }: { destination?: string }) {
  return (
    <Stack
      component={RouterLink}
      to={destination}
      direction="row"
      spacing={1.25}
      alignItems="center"
      color="inherit"
      sx={{ textDecoration: 'none' }}
    >
      <Box component="img" src="/app-logo.svg" alt="" sx={{ width: 42, height: 42 }} />
      <Typography variant="h6" fontWeight={750}>
        SEC Filing Research
      </Typography>
    </Stack>
  );
}

export function PublicHeader({ signIn = true }: { signIn?: boolean }) {
  return (
    <Box
      component="header"
      sx={{ borderBottom: 1, borderColor: 'divider', bgcolor: 'background.paper' }}
    >
      <Container maxWidth="lg">
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          sx={{ minHeight: 72 }}
        >
          <Brand />
          {signIn && (
            <Button href="/api/auth/google/login?policy_acknowledged=true" variant="outlined">
              Sign in
            </Button>
          )}
        </Stack>
      </Container>
    </Box>
  );
}

export function SiteFooter() {
  return (
    <Box component="footer" sx={{ mt: 'auto', borderTop: 1, borderColor: 'divider', py: 2.5 }}>
      <Container maxWidth="lg">
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} justifyContent="space-between">
          <Typography variant="body2" color="text.secondary">
            SEC Filing Research · Not investment advice
          </Typography>
          <Stack direction="row" spacing={2.5} flexWrap="wrap">
            <Link component={RouterLink} to="/privacy">
              Privacy
            </Link>
            <Link component={RouterLink} to="/terms">
              Terms
            </Link>
            <Button
              size="small"
              variant="text"
              startIcon={<CookieOutlined />}
              onClick={showCookiePreferences}
              sx={{ p: 0, minWidth: 0 }}
            >
              Cookie settings
            </Button>
          </Stack>
        </Stack>
      </Container>
    </Box>
  );
}

export function PublicLayout({
  children,
  signIn = true,
}: {
  children: ReactNode;
  signIn?: boolean;
}) {
  return (
    <Stack minHeight="100vh">
      <PublicHeader signIn={signIn} />
      {children}
      <SiteFooter />
    </Stack>
  );
}
