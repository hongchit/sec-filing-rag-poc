import CookieOutlined from '@mui/icons-material/CookieOutlined';
import GitHub from '@mui/icons-material/GitHub';
import MenuIcon from '@mui/icons-material/Menu';
import AccountTreeOutlined from '@mui/icons-material/AccountTreeOutlined';
import {
  Box,
  Button,
  Container,
  IconButton,
  Link,
  ListItemIcon,
  Menu,
  MenuItem,
  Stack,
  Typography,
} from '@mui/material';
import type { ReactNode } from 'react';
import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { showCookiePreferences } from '../consent';
import { InfoOutlined, AssessmentOutlined } from '@mui/icons-material';

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
  const [anchor, setAnchor] = useState<null | HTMLElement>(null);
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
          <Stack direction="row" gap={1} alignItems="center">
            <Stack
              component="nav"
              aria-label="Public"
              direction="row"
              sx={{ display: { xs: 'none', md: 'flex' } }}
            >
              <Button component={RouterLink} to="/overview" startIcon={<InfoOutlined />}>
                Why RAG
              </Button>
              <Button component={RouterLink} to="/how-it-works" startIcon={<AccountTreeOutlined />}>
                How it works
              </Button>
              <Button component={RouterLink} to="/evaluation" startIcon={<AssessmentOutlined />}>
                Evaluation
              </Button>
            </Stack>
            <IconButton
              aria-label="Open navigation"
              onClick={(event) => setAnchor(event.currentTarget)}
              sx={{ display: { md: 'none' } }}
            >
              <MenuIcon />
            </IconButton>
            <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
              {[
                ['Why RAG', '/overview'],
                ['How it works', '/how-it-works'],
                ['Evaluation', '/evaluation'],
              ].map(([label, to]) => (
                <MenuItem key={to} component={RouterLink} to={to} onClick={() => setAnchor(null)}>
                  {to === '/how-it-works' && (
                    <ListItemIcon>
                      <AccountTreeOutlined fontSize="small" />
                    </ListItemIcon>
                  )}
                  {label}
                </MenuItem>
              ))}
            </Menu>
            {signIn && (
              <Button href="/api/auth/google/login?policy_acknowledged=true" variant="outlined">
                Sign in
              </Button>
            )}
          </Stack>
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
            <Link
              href="https://github.com/hongchit/sec-filing-rag-poc"
              target="_blank"
              rel="noreferrer"
              display="inline-flex"
              alignItems="center"
              gap={0.5}
            >
              <GitHub fontSize="small" /> GitHub
            </Link>
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
