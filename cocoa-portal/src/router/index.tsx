import { createBrowserRouter, Navigate } from 'react-router';
import App from '@/App';
import ComposerPage from '@/pages/ComposerPage';
import DebugPage from '@/pages/DebugPage';
import InstanceDetailPage from '@/pages/InstanceDetailPage';
import LoginPage from '@/pages/LoginPage';
import OfficeDetailPage from '@/pages/OfficeDetailPage';
import OfficeListPage from '@/pages/OfficeListPage';
import TopologyPage from '@/pages/TopologyPage';
import { useSessionStore } from '@/stores/session';

function RootRedirect() {
  const token = useSessionStore((state) => state.token);
  return <Navigate to={token === null ? '/login' : '/offices'} replace />;
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
    Component: App,
    children: [
      {
        path: '/offices',
        Component: OfficeListPage,
      },
      {
        path: '/offices/:id',
        Component: OfficeDetailPage,
      },
      {
        path: '/offices/:id/instances/:iid',
        Component: InstanceDetailPage,
      },
      {
        path: '/offices/:id/composer',
        Component: ComposerPage,
      },
      {
        path: '/offices/:id/topology',
        Component: TopologyPage,
      },
      {
        path: '/debug',
        Component: DebugPage,
      },
    ],
  },
]);

export default router;
