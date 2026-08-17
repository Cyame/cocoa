import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router';
import './i18n';
import router from './router';
import './style.css';

const root = document.getElementById('app');
if (!root) throw new Error('Root element not found');
createRoot(root).render(
  <StrictMode>
    {/* D1 修复：App.tsx 用 <Outlet />，必须有 RouterProvider 上下文，否则页面静默空白。 */}
    <RouterProvider router={router} />
  </StrictMode>,
);
