import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import type { CurrentUser } from '@/lib/types';

const SESSION_STORAGE_KEY = 'cocoa.session';

type SessionState = {
  readonly token: string | null;
  readonly user: CurrentUser | null;
  readonly setToken: (token: string, user?: CurrentUser | null) => void;
  readonly clearToken: () => void;
};

type PersistedSession = Pick<SessionState, 'token' | 'user'>;

export const useSessionStore = create<SessionState>()(
  persist<SessionState, [], [], PersistedSession>(
    (set) => ({
      token: null,
      user: null,
      setToken: (token, user = null) => set({ token, user }),
      clearToken: () => set({ token: null, user: null }),
    }),
    {
      name: SESSION_STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      partialize: ({ token, user }) => ({ token, user }),
    },
  ),
);
