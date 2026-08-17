import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import type { CurrentUser } from '@/lib/types';

export const SESSION_STORAGE_KEY = 'eyot.session';

// Persisted-shape version. v1 adds `currentOrgId` to the persisted payload;
// `migrate` backfills v0 sessions (which persisted only {token,user}) so the
// shape change never logs an existing user out.
const SESSION_PERSIST_VERSION = 1;

type SessionState = {
  readonly token: string | null;
  readonly user: CurrentUser | null;
  // v4.3 B5: active org, read by the API layer for X-Organization-Id
  // injection. Persisted so a refresh on /orgs/:orgId/... keeps context.
  // `currentNamespaceId` is deliberately NOT persisted: the namespace is
  // derived from the URL path in the path-based router.
  readonly currentOrgId: string | null;
  readonly currentNamespaceId: string | null;
  readonly setToken: (token: string, user?: CurrentUser | null) => void;
  // B5: switching org clears the namespace — namespaces are org-scoped.
  readonly setCurrentOrg: (orgId: string) => void;
  readonly setCurrentNamespace: (nsId: string | null) => void;
  readonly clearOrgContext: () => void;
  readonly clearToken: () => void;
};

type PersistedSession = Pick<SessionState, 'token' | 'user' | 'currentOrgId'>;

export const useSessionStore = create<SessionState>()(
  persist<SessionState, [], [], PersistedSession>(
    (set) => ({
      token: null,
      user: null,
      currentOrgId: null,
      currentNamespaceId: null,
      setToken: (token, user = null) => set({ token, user }),
      setCurrentOrg: (orgId) => set({ currentOrgId: orgId, currentNamespaceId: null }),
      setCurrentNamespace: (nsId) => set({ currentNamespaceId: nsId }),
      clearOrgContext: () => set({ currentOrgId: null, currentNamespaceId: null }),
      // Logout clears org affinity along with credentials.
      clearToken: () =>
        set({ token: null, user: null, currentOrgId: null, currentNamespaceId: null }),
    }),
    {
      name: SESSION_STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      version: SESSION_PERSIST_VERSION,
      // v0 sessions persisted only {token,user}; backfill currentOrgId to null.
      migrate: (persistedState) => {
        const state = persistedState as Partial<PersistedSession>;
        return {
          token: state.token ?? null,
          user: state.user ?? null,
          currentOrgId: state.currentOrgId ?? null,
        };
      },
      partialize: ({ token, user, currentOrgId }) => ({ token, user, currentOrgId }),
    },
  ),
);

/** Non-reactive read of the active org for the API layer (X-Organization-Id). */
export const getCurrentOrgId = (): string | null => useSessionStore.getState().currentOrgId;
