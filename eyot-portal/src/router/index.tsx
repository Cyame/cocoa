import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { createBrowserRouter, Navigate, useNavigate, useParams } from 'react-router';
import AppShell from '@/components/AppShell';
import { api } from '@/lib/api';
import { fetchWorkspace } from '@/lib/api/workspaces';
import type { Namespace } from '@/lib/types';
import AccountPage from '@/pages/AccountPage';
import BaseClassDetailPage from '@/pages/BaseClassDetailPage';
import BaseClassesPage from '@/pages/BaseClassesPage';
import CapabilitiesPage from '@/pages/CapabilitiesPage';
import DashboardPage from '@/pages/DashboardPage';
import DebugPage from '@/pages/DebugPage';
import ForbiddenPage from '@/pages/ForbiddenPage';
import GenesPage from '@/pages/GenesPage';
import KnowledgePage from '@/pages/KnowledgePage';
import LoginPage from '@/pages/LoginPage';
import NamespaceContractsPage from '@/pages/NamespaceContractsPage';
import NamespaceEntitiesPage from '@/pages/NamespaceEntitiesPage';
import NamespaceInstancesPage from '@/pages/NamespaceInstancesPage';
import NamespaceOverviewPage from '@/pages/NamespaceOverviewPage';
import NamespacesListPage from '@/pages/NamespacesListPage';
import NamespaceWorkspacesPage from '@/pages/NamespaceWorkspacesPage';
import OrgPickerPage from '@/pages/OrgPickerPage';
import WorkspaceIdePage from '@/pages/WorkspaceIdePage';
import WorldMembersPage from '@/pages/WorldMembersPage';
import WorldSettingsPage from '@/pages/WorldSettingsPage';
import { useSessionStore } from '@/stores/session';

function RootRedirect() {
  const token = useSessionStore((state) => state.token);
  const currentOrgId = useSessionStore((state) => state.currentOrgId);
  if (token === null) {
    return <Navigate to="/login" replace />;
  }
  // Persisted org context resumes on the org Dashboard; otherwise the picker.
  return <Navigate to={currentOrgId !== null ? `/orgs/${currentOrgId}` : '/orgs/picker'} replace />;
}

function RequireAuth({ children }: { readonly children: ReactNode }) {
  const token = useSessionStore((state) => state.token);
  if (token === null) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

/**
 * Shared legacy-redirect shell: with an active org we compute the new
 * canonical path (replacing the `:orgId` placeholder); without one there is
 * no org context to attach to, so the safest landing is the org picker
 * (B1 compatibility rule). The template string is compared by value in the
 * dependency list, so a stable literal never retriggers the effect.
 */
function useLegacyOrgRedirect(target: string) {
  const navigate = useNavigate();
  const currentOrgId = useSessionStore((state) => state.currentOrgId);
  const token = useSessionStore((state) => state.token);

  useEffect(() => {
    if (token === null) {
      navigate('/login', { replace: true });
      return;
    }
    if (currentOrgId !== null) {
      navigate(target.replace(':orgId', currentOrgId), { replace: true });
      return;
    }
    navigate('/orgs/picker', { replace: true });
  }, [currentOrgId, navigate, target, token]);
}

export function LegacyNamespacesRedirect() {
  useLegacyOrgRedirect('/orgs/:orgId/namespaces');
  return <RedirectingNote />;
}

export function LegacyOrganizationRedirect() {
  useLegacyOrgRedirect('/orgs/:orgId/settings');
  return <RedirectingNote />;
}

export function LegacyBaseClassRedirect() {
  const { slug } = useParams<{ slug: string }>();
  useLegacyOrgRedirect(`/orgs/:orgId/base-classes/${slug ?? ''}`);
  return <RedirectingNote />;
}

/**
 * /workspaces/:id → /orgs/:orgId/workspaces/:wsId. With an active org the
 * destination is immediate; without one, resolve ws → namespace → org via the
 * API (cheap two hops) and fall back to the picker on failure.
 */
export function LegacyWorkspaceRedirect() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const currentOrgId = useSessionStore((state) => state.currentOrgId);
  const token = useSessionStore((state) => state.token);

  useEffect(() => {
    if (token === null) {
      navigate('/login', { replace: true });
      return;
    }
    let cancelled = false;
    if (currentOrgId !== null) {
      if (id !== undefined) {
        navigate(`/orgs/${currentOrgId}/workspaces/${id}`, { replace: true });
      } else {
        navigate('/orgs/picker', { replace: true });
      }
      return;
    }
    async function resolve() {
      try {
        if (id === undefined) throw new Error('missing workspace id');
        const workspace = await fetchWorkspace(id);
        const namespace = await api<Namespace>(
          `/namespaces/${encodeURIComponent(workspace.namespace_id)}`,
        );
        if (!cancelled) {
          navigate(`/orgs/${namespace.org_id}/workspaces/${id}`, { replace: true });
        }
      } catch {
        if (!cancelled) navigate('/orgs/picker', { replace: true });
      }
    }
    void resolve();
    return () => {
      cancelled = true;
    };
  }, [currentOrgId, id, navigate, token]);

  return <RedirectingNote />;
}

function RedirectingNote() {
  const { t } = useTranslation();
  return (
    <div className="grid min-h-dvh place-items-center bg-slate-100 text-sm text-slate-500">
      {t('legacyRedirect.redirecting')}
    </div>
  );
}

const router = createBrowserRouter([
  {
    path: '/',
    Component: RootRedirect,
  },
  {
    path: '/login',
    Component: LoginPage,
  },
  {
    path: '/403',
    Component: ForbiddenPage,
  },
  {
    path: '/orgs/picker',
    element: (
      <RequireAuth>
        <OrgPickerPage />
      </RequireAuth>
    ),
  },
  {
    path: '/account',
    element: (
      <RequireAuth>
        <AccountPage />
      </RequireAuth>
    ),
  },
  {
    path: '/orgs/:orgId',
    Component: AppShell,
    children: [
      {
        index: true,
        Component: DashboardPage,
      },
      { path: 'settings', Component: WorldSettingsPage },
      { path: 'members', Component: WorldMembersPage },
      { path: 'base-classes', Component: BaseClassesPage },
      { path: 'base-classes/:slug', Component: BaseClassDetailPage },
      { path: 'capabilities', Component: CapabilitiesPage },
      { path: 'genes', Component: GenesPage },
      { path: 'knowledge', Component: KnowledgePage },
      { path: 'namespaces', Component: NamespacesListPage },
      { path: 'namespaces/:nsId', Component: NamespaceOverviewPage },
      { path: 'namespaces/:nsId/workspaces', Component: NamespaceWorkspacesPage },
      { path: 'namespaces/:nsId/entities', Component: NamespaceEntitiesPage },
      { path: 'namespaces/:nsId/instances', Component: NamespaceInstancesPage },
      { path: 'namespaces/:nsId/contracts', Component: NamespaceContractsPage },
      // Param named `id` on purpose: WorkspaceIdePage reads useParams<{ id }>.
      { path: 'workspaces/:id', Component: WorkspaceIdePage },
      { path: 'debug', Component: DebugPage },
    ],
  },
  // Legacy URL redirects — nothing 404s (B1 compatibility).
  { path: '/namespaces', Component: LegacyNamespacesRedirect },
  { path: '/organization', Component: LegacyOrganizationRedirect },
  { path: '/workspaces/:id', Component: LegacyWorkspaceRedirect },
  { path: '/base-classes/:slug', Component: LegacyBaseClassRedirect },
]);

export default router;
