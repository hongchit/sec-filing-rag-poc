import { CircularProgress } from '@mui/material';
import { useEffect, useState, type ReactNode } from 'react';
import { AccountContext, type Account } from './account';
import { Landing } from './pages/Landing';

const nativeFetch = window.fetch.bind(window);
function cookie(name: string): string | undefined {
  return document.cookie
    .split('; ')
    .find((value) => value.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

window.fetch = (input: RequestInfo | URL, init: RequestInit = {}) => {
  const method = (init.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
  const headers = new Headers(
    init.headers ?? (input instanceof Request ? input.headers : undefined),
  );
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = cookie('sec-rag-csrf');
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf));
  }
  return nativeFetch(input, { ...init, headers, credentials: 'same-origin' });
};

export function AuthGate({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<Account | null>();
  useEffect(() => {
    void fetch('/api/auth/me').then(async (response) => {
      setAccount(response.ok ? ((await response.json()) as Account) : null);
    });
  }, []);
  if (account === undefined)
    return <CircularProgress aria-label="Checking authentication" sx={{ m: 4 }} />;
  if (account === null) return <Landing />;
  return <AccountContext.Provider value={account}>{children}</AccountContext.Provider>;
}
