import { AppBar, Box, Container, Toolbar, Typography } from '@mui/material';
import type { ReactNode } from 'react';
import { Link as RouterLink } from 'react-router-dom';
export function AppShell({
  children,
  maxWidth = 'xl',
}: {
  children: ReactNode;
  maxWidth?: 'lg' | 'xl';
}) {
  return (
    <>
      <AppBar position="static" color="primary" elevation={0}>
        <Toolbar>
          <Typography
            component={RouterLink}
            to="/"
            variant="h6"
            color="inherit"
            sx={{ textDecoration: 'none', fontWeight: 750, flexGrow: 1 }}
          >
            SEC Filing RAG
          </Typography>
          <Box component="nav" aria-label="Primary" sx={{ display: 'flex', gap: 3 }}>
            <Typography component={RouterLink} to="/" color="inherit">
              System health
            </Typography>
            <Typography component={RouterLink} to="/evaluation" color="inherit">
              Retrieval evaluation
            </Typography>
          </Box>
        </Toolbar>
      </AppBar>
      <Container component="main" maxWidth={maxWidth} sx={{ py: { xs: 3, md: 5 } }}>
        {children}
      </Container>
    </>
  );
}
