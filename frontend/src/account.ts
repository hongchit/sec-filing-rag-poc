import { createContext, useContext } from 'react';

export type Account = {
  user_id: string;
  email: string;
  display_name?: string | null;
  is_admin: boolean;
  budget: { limit_usd: string; used_usd: string; reserved_usd: string; remaining_usd: string };
  action_reservations: { research_usd: string; corpus_preparation_usd: string };
};

export const AccountContext = createContext<Account | null>(null);
export const useAccount = () => useContext(AccountContext);
