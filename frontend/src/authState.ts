import { createContext, useContext } from 'react';
import type { Account } from './account';

export type AuthState =
  | { status: 'loading'; account: null }
  | { status: 'guest'; account: null }
  | { status: 'authenticated'; account: Account };

export const AuthStateContext = createContext<AuthState>({ status: 'loading', account: null });
export const useAuth = () => useContext(AuthStateContext);
