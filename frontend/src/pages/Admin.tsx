import { Alert, Stack, Tab, Tabs, Typography } from '@mui/material';
import { Link as RouterLink, Navigate, Outlet, useLocation } from 'react-router-dom';
import { AppShell } from '../components/AppShell';

export function Admin() {
  const location = useLocation();
  const active = location.pathname.startsWith('/admin/model-executions')
    ? '/admin/model-executions'
    : '/admin/users';
  return (
    <AppShell>
      <Stack spacing={3}>
        <Typography variant="h1">Administration</Typography>
        <Tabs value={active} aria-label="Administration sections" variant="scrollable">
          <Tab label="Users" value="/admin/users" component={RouterLink} to="/admin/users" />
          <Tab
            label="Operational model executions"
            value="/admin/model-executions"
            component={RouterLink}
            to="/admin/model-executions"
          />
        </Tabs>
        <Outlet />
      </Stack>
    </AppShell>
  );
}

export function AdminIndex() {
  const location = useLocation();
  return <Navigate to={`/admin/users${location.search}`} replace />;
}

export function AdminError({ message }: { message: string }) {
  return <Alert severity="error">{message}</Alert>;
}
