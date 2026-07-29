import { createBrowserRouter, Navigate } from 'react-router';
import AppShell from '@/components/AppShell';
import BaseClassDetailPage from '@/pages/BaseClassDetailPage';
import ForbiddenPage from '@/pages/ForbiddenPage';
import LoginPage from '@/pages/LoginPage';
import NamespacesPage from '@/pages/NamespacesPage';
import OrganizationPage from '@/pages/OrganizationPage';
import WorkspaceIdePage from '@/pages/WorkspaceIdePage';
import { useSessionStore } from '@/stores/session';

function RootRedirect() {
  const token = useSessionStore((state) => state.token);
  return <Navigate to={token === null ? '/login' : '/namespaces'} replace />;
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
    path: '/workspaces/:id',
    Component: WorkspaceIdePage,
  },
  {
    Component: AppShell,
    children: [
      {
        path: '/namespaces',
        Component: NamespacesPage,
      },
      {
        path: '/base-classes/:slug',
        Component: BaseClassDetailPage,
      },
      {
        path: '/organization',
        Component: OrganizationPage,
      },
    ],
  },
]);

export default router;
