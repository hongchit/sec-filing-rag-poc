import { Container } from '@mui/material';
import type { ReactNode } from 'react';
import { OptionalAuth } from '../auth';
import { AppShell } from './AppShell';
import { PublicLayout } from './PublicLayout';

export function PublicOrAppLayout({ children }: { children: ReactNode }) {
  return (
    <OptionalAuth>
      {(account) =>
        account ? (
          <AppShell>{children}</AppShell>
        ) : (
          <PublicLayout>
            <Container component="main" maxWidth="lg" sx={{ py: { xs: 3, md: 5 }, flex: 1 }}>
              {children}
            </Container>
          </PublicLayout>
        )
      }
    </OptionalAuth>
  );
}
