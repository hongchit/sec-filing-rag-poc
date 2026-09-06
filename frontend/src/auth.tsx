import { CircularProgress } from '@mui/material';
import { useContext, useEffect, useState, type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { AccountContext, type Account } from './account';
import { AuthStateContext, type AuthState } from './authState';
import { signInPath } from './returnTo';

const nativeFetch = window.fetch.bind(window);
let redirectingAfterUnauthorized = false;

function cookie(name: string): string | undefined {
  return document.cookie
    .split('; ')
    .find((value) => value.startsWith(`${name}=`))
    ?.slice(name.length + 1);
}

function requestPath(input: RequestInfo | URL): string {
  const value = input instanceof Request ? input.url : String(input);
  try {
    return new URL(value, window.location.origin).pathname;
  } catch {
    return '';
  }
}

function isPublicApi(path: string): boolean {
  return (
    path === '/api/showcase' ||
    path === '/api/retrieval-evaluations/current' ||
    path === '/api/generation-evaluations/current'
  );
}

window.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const method = (init.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
  const headers = new Headers(
    init.headers ?? (input instanceof Request ? input.headers : undefined),
  );
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = cookie('sec-rag-csrf');
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf));
  }
  const response = await nativeFetch(input, { ...init, headers, credentials: 'same-origin' });
  const path = requestPath(input);
  if (
    response.status === 401 &&
    path.startsWith('/api/') &&
    !path.startsWith('/api/auth/') &&
    !isPublicApi(path) &&
    !redirectingAfterUnauthorized
  ) {
    redirectingAfterUnauthorized = true;
    const returnTo = `${window.location.pathname}${window.location.search}`;
    window.location.assign(signInPath(returnTo));
  }
  return response;
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading', account: null });
  useEffect(() => {
    let active = true;
    void fetch('/api/auth/me')
      .then(async (response) => {
        const account = response.ok ? ((await response.json()) as Account) : null;
        if (active)
          setState(
            account ? { status: 'authenticated', account } : { status: 'guest', account: null },
          );
      })
      .catch(() => {
        if (active) setState({ status: 'guest', account: null });
      });
    return () => {
      active = false;
    };
  }, []);
  return <AuthStateContext.Provider value={state}>{children}</AuthStateContext.Provider>;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const state = useContext(AuthStateContext);
  const location = useLocation();
  if (state.status === 'loading')
    return <CircularProgress aria-label="Checking authentication" sx={{ m: 4 }} />;
  if (state.status === 'guest') {
    const returnTo = `${location.pathname}${location.search}`;
    return <Navigate to={signInPath(returnTo)} replace />;
  }
  return <AccountContext.Provider value={state.account}>{children}</AccountContext.Provider>;
}

export function OptionalAuth({ children }: { children: (account: Account | null) => ReactNode }) {
  const state = useContext(AuthStateContext);
  if (state.status === 'loading')
    return <CircularProgress aria-label="Checking authentication" sx={{ m: 4 }} />;
  return state.status === 'authenticated' ? (
    <AccountContext.Provider value={state.account}>
      {children(state.account)}
    </AccountContext.Provider>
  ) : (
    children(null)
  );
}
