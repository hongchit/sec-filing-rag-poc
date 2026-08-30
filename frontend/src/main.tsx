import React from 'react';
import { createRoot } from 'react-dom/client';
import { CssBaseline, ThemeProvider } from '@mui/material';
import { App } from './App';
import { theme } from './theme';
import { initializeConsent } from './consent';
initializeConsent();
const root = document.getElementById('root');
if (root)
  createRoot(root).render(
    <React.StrictMode>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <App authenticate />
      </ThemeProvider>
    </React.StrictMode>,
  );
