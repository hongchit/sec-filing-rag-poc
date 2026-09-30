import AccountBalanceWalletOutlined from '@mui/icons-material/AccountBalanceWalletOutlined';
import AdminPanelSettingsOutlined from '@mui/icons-material/AdminPanelSettingsOutlined';
import AssessmentOutlined from '@mui/icons-material/AssessmentOutlined';
import CookieOutlined from '@mui/icons-material/CookieOutlined';
import DescriptionOutlined from '@mui/icons-material/DescriptionOutlined';
import LogoutOutlined from '@mui/icons-material/LogoutOutlined';
import GitHub from '@mui/icons-material/GitHub';
import MonitorHeartOutlined from '@mui/icons-material/MonitorHeartOutlined';
import TravelExploreOutlined from '@mui/icons-material/TravelExploreOutlined';
import InfoOutlined from '@mui/icons-material/InfoOutlined';
import AccountTreeOutlined from '@mui/icons-material/AccountTreeOutlined';
import MenuIcon from '@mui/icons-material/Menu';
import {
  AppBar,
  Box,
  Button,
  Container,
  Divider,
  IconButton,
  Link,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Stack,
  Toolbar,
} from '@mui/material';
import type { ReactNode } from 'react';
import { useState } from 'react';
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
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.assign('/');
  }
  const destinations = [
    ['Why RAG', '/overview', <InfoOutlined fontSize="small" />],
    ['How it works', '/how-it-works', <AccountTreeOutlined fontSize="small" />],
    ['Query', '/research', <TravelExploreOutlined fontSize="small" />],
    ['Library', '/corpus', <DescriptionOutlined fontSize="small" />],
    ['Evaluation', '/evaluation', <AssessmentOutlined fontSize="small" />],
    ['Status', '/diagnostics/health', <MonitorHeartOutlined fontSize="small" />],
    ...(account?.is_admin
      ? ([['Admin', '/admin/users', <AdminPanelSettingsOutlined fontSize="small" />]] as const)
      : []),
  ] as const;
  return (
    <Stack minHeight="100vh">
      <AppBar position="static" color="primary" elevation={0}>
        <Toolbar sx={{ gap: 1 }}>
          <Box sx={{ flexGrow: 1 }}>
            <Brand destination="/" />
          </Box>
          <Box
            component="nav"
            aria-label="Primary"
            sx={{
              display: account?.is_admin ? { xs: 'none', xl: 'flex' } : { xs: 'none', lg: 'flex' },
              gap: 1,
              alignItems: 'center',
              justifyContent: 'flex-end',
            }}
          >
            <Button
              color="inherit"
              component={RouterLink}
              to="/overview"
              startIcon={<InfoOutlined />}
            >
              Why RAG
            </Button>
            <Button
              color="inherit"
              component={RouterLink}
              to="/how-it-works"
              startIcon={<AccountTreeOutlined />}
            >
              How it works
            </Button>
            <Button
              color="inherit"
              component={RouterLink}
              to="/research"
              startIcon={<TravelExploreOutlined />}
            >
              Query
            </Button>
            <Button
              color="inherit"
              component={RouterLink}
              to="/corpus"
              startIcon={<DescriptionOutlined />}
            >
              Library
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
            <Button
              color="inherit"
              component={RouterLink}
              to="/profile"
              aria-label={`View profile, ${Number(account?.budget?.remaining_usd ?? 0).toFixed(2)} dollars budget left`}
              startIcon={<AccountBalanceWalletOutlined />}
              sx={{ opacity: 0.85, display: 'flex', alignItems: 'center', gap: 0.5 }}
            >
              ${Number(account?.budget?.remaining_usd ?? 0).toFixed(2)} left
            </Button>
            <Button color="inherit" onClick={() => void logout()} startIcon={<LogoutOutlined />}>
              Logout
            </Button>
          </Box>
          <IconButton
            color="inherit"
            aria-label="Open application navigation"
            aria-controls={menuAnchor ? 'application-navigation-menu' : undefined}
            aria-expanded={Boolean(menuAnchor)}
            onClick={(event) => setMenuAnchor(event.currentTarget)}
            sx={{
              display: account?.is_admin ? { xs: 'inline-flex', xl: 'none' } : { lg: 'none' },
              flexShrink: 0,
            }}
          >
            <MenuIcon />
          </IconButton>
          <Menu
            id="application-navigation-menu"
            anchorEl={menuAnchor}
            open={Boolean(menuAnchor)}
            onClose={() => setMenuAnchor(null)}
            slotProps={{ paper: { sx: { minWidth: 240, maxWidth: 'calc(100vw - 32px)' } } }}
          >
            {destinations.map(([label, to, icon]) => (
              <MenuItem key={to} component={RouterLink} to={to} onClick={() => setMenuAnchor(null)}>
                <ListItemIcon>{icon}</ListItemIcon>
                <ListItemText>{label}</ListItemText>
              </MenuItem>
            ))}
            <Divider />
            <MenuItem component={RouterLink} to="/profile" onClick={() => setMenuAnchor(null)}>
              <ListItemIcon>
                <AccountBalanceWalletOutlined fontSize="small" />
              </ListItemIcon>
              <ListItemText>
                ${Number(account?.budget?.remaining_usd ?? 0).toFixed(2)} left
              </ListItemText>
            </MenuItem>
            <MenuItem
              onClick={() => {
                setMenuAnchor(null);
                void logout();
              }}
            >
              <ListItemIcon>
                <LogoutOutlined fontSize="small" />
              </ListItemIcon>
              <ListItemText>Logout</ListItemText>
            </MenuItem>
          </Menu>
        </Toolbar>
      </AppBar>
      <Container
        component="main"
        maxWidth={maxWidth}
        sx={{ py: { xs: 3, md: 5 }, flex: 1, minWidth: 0, overflowWrap: 'anywhere' }}
      >
        {children}
      </Container>
      <Box component="footer" sx={{ borderTop: 1, borderColor: 'divider', py: 2.5 }}>
        <Container maxWidth={maxWidth}>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={2.5}
            alignItems={{ xs: 'flex-start', sm: 'center' }}
            flexWrap="wrap"
            useFlexGap
          >
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
            <Button size="small" startIcon={<CookieOutlined />} onClick={showCookiePreferences}>
              Cookie settings
            </Button>
          </Stack>
        </Container>
      </Box>
    </Stack>
  );
}
