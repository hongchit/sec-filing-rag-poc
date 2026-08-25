import { createTheme } from '@mui/material/styles';

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#174c3c', dark: '#0d3529', light: '#dcebe5' },
    background: { default: '#f4f6f4', paper: '#fff' },
    success: { main: '#287a4b' },
    warning: { main: '#a45b0a' },
    error: { main: '#a12c35' },
    text: { primary: '#17221e', secondary: '#53605b' },
    divider: '#d9dfdc',
  },
  typography: {
    fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    h1: { fontSize: 'clamp(2rem, 5vw, 3.4rem)', fontWeight: 750, letterSpacing: '-.04em' },
    h2: { fontSize: 'clamp(1.35rem, 3vw, 2rem)', fontWeight: 700 },
    h3: { fontSize: '1.1rem', fontWeight: 700 },
    button: { textTransform: 'none', fontWeight: 650 },
  },
  shape: { borderRadius: 10 },
  spacing: 8,
  components: {
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
    MuiCard: { styleOverrides: { root: { border: '1px solid #d9dfdc', boxShadow: 'none' } } },
    MuiAccordion: {
      styleOverrides: {
        root: { border: '1px solid #d9dfdc', boxShadow: 'none', '&:before': { display: 'none' } },
      },
    },
    MuiChip: { defaultProps: { size: 'small' } },
    MuiAlert: { styleOverrides: { root: { alignItems: 'flex-start' } } },
  },
});
