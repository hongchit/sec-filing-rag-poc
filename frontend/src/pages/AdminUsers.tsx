import { Alert, Button, Link, Paper, Stack, TextField, Typography } from '@mui/material';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { AdminError } from './Admin';

type User = {
  id: string;
  email: string;
  display_name?: string | null;
  status: 'active' | 'disabled';
  lifetime_budget_override_usd?: string | null;
  budget: { limit_usd: string; used_usd: string; reserved_usd: string; remaining_usd: string };
};
type Activity = {
  research: {
    id: string;
    ticker: string;
    question: string;
    status: string;
    charged_usd?: string;
  }[];
  filing_batches: {
    id: string;
    mode: string;
    fiscal_year?: number;
    status: string;
    request_id?: string | null;
    kestra_execution_id?: string | null;
    safe_error?: string | null;
    charged_usd?: string;
    items: {
      id: string;
      ticker: string;
      status: string;
      selected_accession?: string | null;
      acquisition_id?: string | null;
      corpus_version_id?: string | null;
      safe_error?: string | null;
    }[];
  }[];
};

export function AdminUsers() {
  const [searchParams, setSearchParams] = useSearchParams();
  const restoredUserId = useRef(searchParams.get('user')).current;
  const [users, setUsers] = useState<User[]>([]);
  const [selected, setSelected] = useState<User>();
  const [activity, setActivity] = useState<Activity>();
  const [budget, setBudget] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const show = useCallback(async (user: User) => {
    setSelected(user);
    setActivity(undefined);
    setBudget(user.lifetime_budget_override_usd ?? '');
    setError('');
    const response = await fetch(`/api/admin/users/${user.id}/activity`);
    if (!response.ok) {
      setError(
        response.status === 403
          ? 'Administrator access is required.'
          : 'User activity could not be loaded.',
      );
      return;
    }
    setActivity((await response.json()) as Activity);
  }, []);

  const loadUsers = useCallback(
    async (preferredUserId = restoredUserId) => {
      setLoading(true);
      setError('');
      const response = await fetch('/api/admin/users');
      setLoading(false);
      if (!response.ok) {
        setError(
          response.status === 403
            ? 'Administrator access is required.'
            : 'Users could not be loaded.',
        );
        return;
      }
      const values = ((await response.json()) as { items: User[] }).items;
      setUsers(values);
      const restored = values.find((user) => user.id === preferredUserId);
      if (restored) await show(restored);
    },
    [restoredUserId, show],
  );

  async function select(user: User) {
    setSearchParams({ user: user.id });
    await show(user);
  }
  async function update(body: object) {
    if (!selected) return;
    setMessage('');
    const response = await fetch(`/api/admin/users/${selected.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    setMessage(response.ok ? 'Account updated.' : 'Account update failed.');
    if (response.ok) await loadUsers(selected.id);
  }
  useEffect(() => void loadUsers(), [loadUsers]);

  if (loading) return <Typography>Loading users…</Typography>;
  if (error && users.length === 0) return <AdminError message={error} />;
  return (
    <Stack spacing={3}>
      <Stack spacing={0.5}>
        <Typography variant="h2">Users</Typography>
        <Typography color="text.secondary">
          Manage account access, lifetime allowances, and user activity.
        </Typography>
      </Stack>
      {message && <Alert severity="info">{message}</Alert>}
      {error && <AdminError message={error} />}
      {users.length === 0 ? (
        <Typography>No users recorded.</Typography>
      ) : (
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} alignItems="flex-start">
          <Paper variant="outlined" sx={{ width: { xs: '100%', md: 360 }, p: 1 }}>
            <Stack spacing={0.5}>
              {users.map((user) => (
                <Button
                  key={user.id}
                  onClick={() => void select(user)}
                  variant={selected?.id === user.id ? 'contained' : 'text'}
                  aria-current={selected?.id === user.id ? 'true' : undefined}
                  sx={{ justifyContent: 'flex-start', textAlign: 'left' }}
                >
                  {user.email} · {user.status} · ${Number(user.budget.remaining_usd).toFixed(2)}{' '}
                  left
                </Button>
              ))}
            </Stack>
          </Paper>
          {!selected && (
            <Paper variant="outlined" sx={{ p: 3, flexGrow: 1 }}>
              <Typography>Select a user to view account details and activity.</Typography>
            </Paper>
          )}
          {selected && (
            <Paper sx={{ p: 3, flexGrow: 1, minWidth: 0 }}>
              <Stack spacing={2}>
                <Typography variant="h2">{selected.display_name || selected.email}</Typography>
                <Typography>
                  {selected.email} · {selected.status}
                </Typography>
                <Typography>
                  Used ${selected.budget.used_usd}; reserved ${selected.budget.reserved_usd}; limit
                  ${selected.budget.limit_usd}
                </Typography>
                <Stack direction={{ xs: 'column', lg: 'row' }} spacing={1}>
                  <Button
                    variant="outlined"
                    onClick={() =>
                      void update({ status: selected.status === 'active' ? 'disabled' : 'active' })
                    }
                  >
                    {selected.status === 'active' ? 'Disable user' : 'Enable user'}
                  </Button>
                  <TextField
                    label="Lifetime budget override (USD)"
                    value={budget}
                    onChange={(event) => setBudget(event.target.value)}
                    size="small"
                  />
                  <Button onClick={() => void update({ lifetime_budget_override_usd: budget })}>
                    Set override
                  </Button>
                  <Button onClick={() => void update({ clear_budget_override: true })}>
                    Use default
                  </Button>
                </Stack>
                {!activity && !error ? (
                  <Typography>Loading user activity…</Typography>
                ) : activity ? (
                  <UserActivity activity={activity} />
                ) : null}
              </Stack>
            </Paper>
          )}
        </Stack>
      )}
    </Stack>
  );
}

function UserActivity({ activity }: { activity: Activity }) {
  return (
    <>
      <Typography variant="h3">Research questions</Typography>
      {activity.research.length === 0 && <Typography>No research recorded.</Typography>}
      {activity.research.map((item, index) => (
        <Typography key={item.id}>
          {index + 1}. {item.ticker} ·{' '}
          <Link component={RouterLink} to={`/research/${item.id}`}>
            {item.question}
          </Link>{' '}
          · {item.status} · ${item.charged_usd ?? 'reserved'}
        </Typography>
      ))}
      <Typography variant="h3">Corpus preparations</Typography>
      {activity.filing_batches.length === 0 && (
        <Typography>No corpus preparations recorded.</Typography>
      )}
      {activity.filing_batches.map((batch, index) => (
        <Paper key={batch.id} variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={0.5}>
            <Typography>
              {index + 1}. {batch.mode} {batch.fiscal_year ?? ''} ·{' '}
              {batch.items.length > 0 && batch.items.every((item) => item.status === 'skipped')
                ? 'skipped'
                : batch.status}{' '}
              · ${batch.charged_usd ?? 'reserved'}
            </Typography>
            <Typography variant="caption">Batch ID: {batch.id}</Typography>
            {batch.request_id && (
              <Typography variant="caption">Request ID: {batch.request_id}</Typography>
            )}
            {batch.kestra_execution_id && (
              <Typography variant="caption">
                Kestra execution: {batch.kestra_execution_id}
              </Typography>
            )}
            {batch.safe_error && <Alert severity="error">{batch.safe_error}</Alert>}
            {batch.items.map((item) => (
              <Stack key={item.id} spacing={0.25} sx={{ pt: 1 }}>
                <Typography>
                  {item.corpus_version_id && item.status === 'succeeded' ? (
                    <Link
                      component={RouterLink}
                      to={`/corpus/${item.ticker}/1?corpus=${item.corpus_version_id}`}
                    >
                      {item.ticker}
                    </Link>
                  ) : (
                    item.ticker
                  )}{' '}
                  · {item.status}
                </Typography>
                <Typography variant="caption">Item ID: {item.id}</Typography>
                {item.selected_accession && (
                  <Typography variant="caption">Accession: {item.selected_accession}</Typography>
                )}
                {item.acquisition_id && (
                  <Typography variant="caption">Acquisition ID: {item.acquisition_id}</Typography>
                )}
                {item.corpus_version_id && (
                  <Typography variant="caption">Corpus ID: {item.corpus_version_id}</Typography>
                )}
                {item.safe_error && (
                  <Alert severity={item.status === 'skipped' ? 'info' : 'error'}>
                    {item.safe_error}
                  </Alert>
                )}
              </Stack>
            ))}
          </Stack>
        </Paper>
      ))}
    </>
  );
}
