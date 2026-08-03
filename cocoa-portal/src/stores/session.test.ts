import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { CurrentUser } from '@/lib/types';
import { getCurrentOrgId, SESSION_STORAGE_KEY, useSessionStore } from '@/stores/session';

const OLD_USER: CurrentUser = {
  user_id: 'user-1',
  username: 'old-user',
  is_super_admin: false,
  token: null,
};

beforeEach(() => {
  localStorage.clear();
  useSessionStore.setState({
    token: null,
    user: null,
    currentOrgId: null,
    currentNamespaceId: null,
  });
});

afterEach(() => {
  localStorage.clear();
});

describe('org context actions', () => {
  it('setCurrentOrg sets the org and clears the namespace', () => {
    useSessionStore.getState().setCurrentNamespace('ns-1');
    useSessionStore.getState().setCurrentOrg('org-2');
    const state = useSessionStore.getState();
    expect(state.currentOrgId).toBe('org-2');
    expect(state.currentNamespaceId).toBeNull();
  });

  it('setCurrentNamespace sets and clears the namespace', () => {
    useSessionStore.getState().setCurrentNamespace('ns-1');
    expect(useSessionStore.getState().currentNamespaceId).toBe('ns-1');
    useSessionStore.getState().setCurrentNamespace(null);
    expect(useSessionStore.getState().currentNamespaceId).toBeNull();
  });

  it('clearOrgContext clears org and namespace', () => {
    useSessionStore.getState().setCurrentOrg('org-1');
    useSessionStore.getState().setCurrentNamespace('ns-1');
    useSessionStore.getState().clearOrgContext();
    const state = useSessionStore.getState();
    expect(state.currentOrgId).toBeNull();
    expect(state.currentNamespaceId).toBeNull();
  });

  it('clearToken clears org affinity along with credentials', () => {
    useSessionStore.setState({
      token: 'jwt',
      user: OLD_USER,
      currentOrgId: 'org-1',
      currentNamespaceId: 'ns-1',
    });
    useSessionStore.getState().clearToken();
    const state = useSessionStore.getState();
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();
    expect(state.currentOrgId).toBeNull();
    expect(state.currentNamespaceId).toBeNull();
  });
});

describe('getCurrentOrgId helper', () => {
  it('reads the active org non-reactively', () => {
    expect(getCurrentOrgId()).toBeNull();
    useSessionStore.getState().setCurrentOrg('org-1');
    expect(getCurrentOrgId()).toBe('org-1');
  });
});

describe('persistence', () => {
  it('persists currentOrgId and rehydrates it', async () => {
    localStorage.setItem(
      SESSION_STORAGE_KEY,
      JSON.stringify({
        state: { token: 'jwt-persisted', user: null, currentOrgId: 'org-persisted' },
        version: 1,
      }),
    );
    await useSessionStore.persist.rehydrate();
    const state = useSessionStore.getState();
    expect(state.token).toBe('jwt-persisted');
    expect(state.currentOrgId).toBe('org-persisted');
    expect(state.currentNamespaceId).toBeNull();
  });

  it('rehydrates a version-0 session (no currentOrgId) without error or logout', async () => {
    localStorage.setItem(
      SESSION_STORAGE_KEY,
      JSON.stringify({
        state: { token: 'old-jwt', user: OLD_USER },
        version: 0,
      }),
    );
    await useSessionStore.persist.rehydrate();
    const state = useSessionStore.getState();
    expect(state.token).toBe('old-jwt');
    expect(state.user).toEqual(OLD_USER);
    expect(state.currentOrgId).toBeNull();
    expect(state.currentNamespaceId).toBeNull();
  });

  it('rehydrates an unversioned stored session (pre-persist-version shape) without error', async () => {
    localStorage.setItem(
      SESSION_STORAGE_KEY,
      JSON.stringify({
        state: { token: 'legacy-jwt', user: null },
      }),
    );
    await useSessionStore.persist.rehydrate();
    const state = useSessionStore.getState();
    expect(state.token).toBe('legacy-jwt');
    expect(state.currentOrgId).toBeNull();
    expect(state.currentNamespaceId).toBeNull();
  });

  it('does not persist currentNamespaceId', () => {
    useSessionStore.getState().setCurrentOrg('org-1');
    useSessionStore.getState().setCurrentNamespace('ns-1');
    const stored = JSON.parse(localStorage.getItem(SESSION_STORAGE_KEY) ?? '{}') as {
      state: Record<string, unknown>;
    };
    expect(stored.state.currentOrgId).toBe('org-1');
    expect(stored.state).not.toHaveProperty('currentNamespaceId');
  });
});
