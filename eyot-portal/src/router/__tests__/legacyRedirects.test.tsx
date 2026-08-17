import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import {
  LegacyBaseClassRedirect,
  LegacyNamespacesRedirect,
  LegacyOrganizationRedirect,
  LegacyWorkspaceRedirect,
} from '@/router/index';
import { useSessionStore } from '@/stores/session';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

vi.mock('@/lib/api/workspaces', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/workspaces')>();
  return { ...actual, fetchWorkspace: vi.fn() };
});

function renderLegacy(initialPath: string, element: ReactElement, routePath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path={routePath} element={element} />
        <Route path="/orgs/picker" element={<p>Org picker destination</p>} />
        <Route path="/orgs/:orgId/namespaces" element={<p>Namespaces destination</p>} />
        <Route path="/orgs/:orgId/settings" element={<p>Settings destination</p>} />
        <Route path="/orgs/:orgId/base-classes/:slug" element={<p>Base class destination</p>} />
        <Route path="/orgs/:orgId/workspaces/:wsId" element={<p>Workspace destination</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(api).mockReset();
  useSessionStore.setState({
    token: 'jwt',
    user: null,
    currentOrgId: 'org-1',
    currentNamespaceId: null,
  });
});

describe('legacy URL redirects (B1 compatibility)', () => {
  it('/namespaces redirects to the active org namespaces list', async () => {
    renderLegacy('/namespaces', <LegacyNamespacesRedirect />, '/namespaces');

    expect(await screen.findByText('Namespaces destination')).toBeInTheDocument();
  });

  it('/organization redirects to the active org settings', async () => {
    renderLegacy('/organization', <LegacyOrganizationRedirect />, '/organization');

    expect(await screen.findByText('Settings destination')).toBeInTheDocument();
  });

  it('/base-classes/:slug redirects keeping the slug', async () => {
    renderLegacy('/base-classes/astro', <LegacyBaseClassRedirect />, '/base-classes/:slug');

    expect(await screen.findByText('Base class destination')).toBeInTheDocument();
  });

  it('/workspaces/:id redirects into the active org without an API hop', async () => {
    renderLegacy('/workspaces/ws-9', <LegacyWorkspaceRedirect />, '/workspaces/:id');

    expect(await screen.findByText('Workspace destination')).toBeInTheDocument();
    expect(vi.mocked(api)).not.toHaveBeenCalled();
  });

  it('falls back to the org picker when no org context is active', async () => {
    useSessionStore.setState({ currentOrgId: null });
    renderLegacy('/namespaces', <LegacyNamespacesRedirect />, '/namespaces');

    expect(await screen.findByText('Org picker destination')).toBeInTheDocument();
  });
});
