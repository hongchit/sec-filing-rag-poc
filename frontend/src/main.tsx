import { createRoot } from 'react-dom/client';
import { CssBaseline, ThemeProvider } from '@mui/material';
import { App } from './App';
import { initializeOutboundClickTracking } from './analytics';
import { theme } from './theme';
import { initializeConsent } from './consent';
initializeOutboundClickTracking();
initializeConsent();
const root = document.getElementById('root');
if (root)
  createRoot(root).render(
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App authenticate />
    </ThemeProvider>,
  );
