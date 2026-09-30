import AccountCircleOutlined from '@mui/icons-material/AccountCircleOutlined';
import AccountBalanceWalletOutlined from '@mui/icons-material/AccountBalanceWalletOutlined';
import { Alert, Box, Card, CardContent, Chip, Paper, Stack, Typography } from '@mui/material';
import { useEffect } from 'react';
import { useAccount } from '../account';
import { AppShell } from '../components/AppShell';

const usd = (value: string | undefined) => `$${Number(value ?? 0).toFixed(2)}`;

export function Profile() {
  const account = useAccount();
  const name = account?.display_name?.trim();

  useEffect(() => {
    document.title = 'Your profile · SEC Filing Research';
    return () => {
      document.title = 'SEC Filing RAG';
    };
  }, []);

  return (
    <AppShell maxWidth="lg">
      <Stack spacing={4}>
        <Box>
          <Typography variant="overline" color="primary">
            Your account
          </Typography>
          <Typography component="h1" variant="h1">
            {name ? `Welcome, ${name}.` : 'Welcome.'}
          </Typography>
          <Typography variant="h6" color="text.secondary" fontWeight={400} mt={1}>
            Review your signed-in identity and evaluation-platform allowance.
          </Typography>
        </Box>

        <Paper component="section" sx={{ p: { xs: 2.5, md: 3 } }}>
          <Stack direction={{ xs: 'column', sm: 'row' }} gap={2} alignItems={{ sm: 'center' }}>
            <AccountCircleOutlined color="primary" sx={{ fontSize: 48 }} aria-hidden="true" />
            <Box flex={1} minWidth={0}>
              <Typography variant="overline" color="text.secondary">
                Signed in as
              </Typography>
              {name && <Typography variant="h2">{name}</Typography>}
              <Typography sx={{ overflowWrap: 'anywhere' }}>{account?.email}</Typography>
            </Box>
            {account?.is_admin && <Chip color="primary" label="Administrator" />}
          </Stack>
        </Paper>

        <Box component="section" aria-labelledby="budget-heading">
          <Stack direction="row" gap={1} alignItems="center" mb={2}>
            <AccountBalanceWalletOutlined color="primary" aria-hidden="true" />
            <Typography id="budget-heading" variant="h2">
              Your evaluation budget
            </Typography>
          </Stack>
          <Box display="grid" gridTemplateColumns={{ xs: '1fr 1fr', md: 'repeat(4, 1fr)' }} gap={2}>
            {[
              ['Available', usd(account?.budget.remaining_usd)],
              ['Used', usd(account?.budget.used_usd)],
              ['Reserved', usd(account?.budget.reserved_usd)],
              ['Lifetime limit', usd(account?.budget.limit_usd)],
            ].map(([label, value]) => (
              <Card key={label}>
                <CardContent>
                  <Typography variant="overline" color="text.secondary">
                    {label}
                  </Typography>
                  <Typography variant="h2">{value}</Typography>
                </CardContent>
              </Card>
            ))}
          </Box>
          <Alert severity="info" sx={{ mt: 2 }}>
            <Typography fontWeight={750}>
              A limited allowance for evaluating the platform
            </Typography>
            <Typography mt={0.5}>
              This is a shared evaluation environment, so every user receives a limited lifetime
              quota for model-backed queries and filing preparation. It is a platform usage
              allowance, not an amount you will be billed.
            </Typography>
            <Typography mt={1}>
              Reserved funds are set aside for work in progress or awaiting usage reconciliation;
              completed work is reflected under Used. You can continue viewing existing research,
              filings, and public evaluation results without starting new model work.
            </Typography>
          </Alert>
        </Box>
      </Stack>
    </AppShell>
  );
}
