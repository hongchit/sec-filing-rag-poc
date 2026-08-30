import AccountBalanceWalletOutlined from '@mui/icons-material/AccountBalanceWalletOutlined';
import AdminPanelSettingsOutlined from '@mui/icons-material/AdminPanelSettingsOutlined';
import AssessmentOutlined from '@mui/icons-material/AssessmentOutlined';
import CookieOutlined from '@mui/icons-material/CookieOutlined';
import DescriptionOutlined from '@mui/icons-material/DescriptionOutlined';
import LogoutOutlined from '@mui/icons-material/LogoutOutlined';
import MonitorHeartOutlined from '@mui/icons-material/MonitorHeartOutlined';
import TravelExploreOutlined from '@mui/icons-material/TravelExploreOutlined';
import { AppBar, Box, Button, Container, Link, Stack, Toolbar, Typography } from '@mui/material';
import type { ReactNode } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useAccount } from '../account';
import { showCookiePreferences } from '../consent';
import { Brand } from './PublicLayout';
export function AppShell({
  children,
  maxWidth = 'xl',
}: {
  children: ReactNode;
  maxWidth?: 'lg' | 'xl';
}) {
  const account = useAccount();
  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.assign('/');
  }
  return (
    <>
      <AppBar position="static" color="primary" elevation={0}>
        <Toolbar>
          <Box sx={{ flexGrow: 1 }}>
            <Brand destination="/research" />
          </Box>
          <Box
            component="nav"
            aria-label="Primary"
            sx={{
              display: 'flex',
              gap: { xs: 1, lg: 2 },
              alignItems: 'center',
              flexWrap: 'wrap',
              justifyContent: 'flex-end',
            }}
          >
            <Button
              color="inherit"
              component={RouterLink}
              to="/research"
              startIcon={<TravelExploreOutlined />}
            >
              Research
            </Button>
            <Button
              color="inherit"
              component={RouterLink}
              to="/corpus"
              startIcon={<DescriptionOutlined />}
            >
              Corpus
            </Button>
            <Button
              color="inherit"
              component={RouterLink}
              to="/evaluation"
              startIcon={<AssessmentOutlined />}
            >
              Evaluation
            </Button>
            <Button
              color="inherit"
              component={RouterLink}
              to="/diagnostics/health"
              startIcon={<MonitorHeartOutlined />}
            >
              Status
            </Button>
            {account?.is_admin && (
              <Button
                color="inherit"
                component={RouterLink}
                to="/admin/users"
                startIcon={<AdminPanelSettingsOutlined />}
              >
                Admin
              </Button>
            )}
            <Typography
              color="inherit"
              sx={{ opacity: 0.85, display: 'flex', alignItems: 'center', gap: 0.5 }}
            >
              <AccountBalanceWalletOutlined fontSize="small" />$
              {Number(account?.budget.remaining_usd ?? 0).toFixed(2)} left
            </Typography>
            <Button color="inherit" onClick={() => void logout()} startIcon={<LogoutOutlined />}>
              Logout
            </Button>
          </Box>
        </Toolbar>
      </AppBar>
      <Container component="main" maxWidth={maxWidth} sx={{ py: { xs: 3, md: 5 } }}>
        {children}
      </Container>
      <Box component="footer" sx={{ borderTop: 1, borderColor: 'divider', py: 2.5 }}>
        <Container maxWidth={maxWidth}>
          <Stack direction="row" spacing={2.5} alignItems="center" flexWrap="wrap">
            <Link component={RouterLink} to="/privacy">
              Privacy
            </Link>
            <Link component={RouterLink} to="/terms">
              Terms
            </Link>
            <Button size="small" startIcon={<CookieOutlined />} onClick={showCookiePreferences}>
              Cookie settings
            </Button>
          </Stack>
        </Container>
      </Box>
    </>
  );
}
