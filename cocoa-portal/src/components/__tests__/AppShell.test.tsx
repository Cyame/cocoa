import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AppShell from '@/components/AppShell';
import { api } from '@/lib/api';
import { useSessionStore } from '@/stores/session';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

const ME_PAYLOAD = {
  id: 'user-1',
  username: 'operator',
  nickname: null,
  email: 'op@test.local',
  is_super_admin: false,
  identity: 'member',
  locked_gene_slugs: [],
  extra_gene_slugs: [],
  org_identity: {
    organization_id: 'org-1',
    atoms: ['can_edit_workspace'],
    display_label: 'editor',
  },
};

function renderShell(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/orgs/:orgId" element={<AppShell />}>
          <Route index element={<p>Dashboard destination</p>} />
          <Route path="namespaces" element={<p>Namespaces destination</p>} />
          <Route path="namespaces/:nsId" element={<p>Namespace destination</p>} />
          <Route path="namespaces/:nsId/workspaces" element={<p>Workspaces destination</p>} />
        </Route>
        <Route path="/account" element={<p>Account destination</p>} />
        <Route path="/login" element={<p>Login destination</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

/** The desktop sidebar — the mobile strip is CSS-hidden in real layouts. */
function desktopNav() {
  return within(screen.getByRole('navigation', { name: 'Primary' }));
}

beforeEach(() => {
  mockedApi.mockReset();
  mockedApi.mockResolvedValue(ME_PAYLOAD);
  useSessionStore.setState({
    token: 'jwt',
    user: {
      user_id: 'user-1',
      username: 'operator',
      identity: 'member',
      is_super_admin: false,
      token: 'jwt',
    },
    currentOrgId: null,
    currentNamespaceId: null,
  });
});

describe('AppShell sidebar sections', () => {
  it('renders the World section when an org context is active', () => {
    useSessionStore.setState({ currentOrgId: 'org-1' });
    renderShell('/orgs/org-1');

    const nav = desktopNav();
    expect(nav.getByRole('link', { name: 'Dashboard' })).toHaveAttribute('href', '/orgs/org-1');
    expect(nav.getByRole('link', { name: 'Settings' })).toHaveAttribute(
      'href',
      '/orgs/org-1/settings',
    );
    expect(nav.getByRole('link', { name: 'Members' })).toHaveAttribute(
      'href',
      '/orgs/org-1/members',
    );
    expect(nav.getByRole('link', { name: 'Deity' })).toHaveAttribute(
      'href',
      '/orgs/org-1/base-classes',
    );
    expect(nav.getByRole('link', { name: 'Capabilities' })).toHaveAttribute(
      'href',
      '/orgs/org-1/capabilities',
    );
    expect(nav.getByRole('link', { name: 'Gene' })).toHaveAttribute('href', '/orgs/org-1/genes');
    expect(nav.getByRole('link', { name: 'Namespaces' })).toHaveAttribute(
      'href',
      '/orgs/org-1/namespaces',
    );
    expect(nav.getByRole('link', { name: 'Debug' })).toHaveAttribute('href', '/orgs/org-1/debug');
  });

  it('renders the Current namespace section with its switcher when a namespace is active', () => {
    useSessionStore.setState({ currentOrgId: 'org-1', currentNamespaceId: 'ns-1' });
    renderShell('/orgs/org-1/namespaces/ns-1/workspaces');

    expect(screen.getByTestId('namespace-switcher')).toBeInTheDocument();
    const nav = desktopNav();
    expect(nav.getByRole('link', { name: 'Workspaces' })).toHaveAttribute(
      'href',
      '/orgs/org-1/namespaces/ns-1/workspaces',
    );
    expect(nav.getByRole('link', { name: 'Entity' })).toHaveAttribute(
      'href',
      '/orgs/org-1/namespaces/ns-1/entities',
    );
    expect(nav.getByRole('link', { name: 'Instances' })).toHaveAttribute(
      'href',
      '/orgs/org-1/namespaces/ns-1/instances',
    );
    expect(nav.getByRole('link', { name: 'Contract' })).toHaveAttribute(
      'href',
      '/orgs/org-1/namespaces/ns-1/contracts',
    );
    expect(nav.queryByRole('link', { name: 'Topology' })).not.toBeInTheDocument();
  });

  it('does not render the namespace section when only an org is set', () => {
    useSessionStore.setState({ currentOrgId: 'org-1', currentNamespaceId: null });
    renderShell('/orgs/org-1');

    expect(screen.queryByTestId('namespace-switcher')).not.toBeInTheDocument();
    expect(desktopNav().queryByRole('link', { name: 'Workspaces' })).not.toBeInTheDocument();
  });

  it('renders the org switcher and account links in the header area', () => {
    useSessionStore.setState({ currentOrgId: 'org-1' });
    renderShell('/orgs/org-1');

    expect(screen.getByTestId('org-switcher')).toBeInTheDocument();
    expect(desktopNav().getByRole('link', { name: 'Account' })).toBeInTheDocument();
  });
});

describe('AppShell route → session sync', () => {
  it('entering /orgs/:orgId sets currentOrgId in the session store', async () => {
    useSessionStore.setState({ currentOrgId: null, currentNamespaceId: null });
    renderShell('/orgs/org-1');

    await waitFor(() => expect(useSessionStore.getState().currentOrgId).toBe('org-1'));
  });

  it('clears currentNamespaceId on an org-level route', async () => {
    useSessionStore.setState({ currentOrgId: 'org-1', currentNamespaceId: 'ns-1' });
    renderShell('/orgs/org-1/namespaces');

    await waitFor(() => expect(useSessionStore.getState().currentNamespaceId).toBeNull());
  });

  it('syncs currentNamespaceId from a namespaces/:nsId route', async () => {
    useSessionStore.setState({ currentOrgId: 'org-1', currentNamespaceId: null });
    renderShell('/orgs/org-1/namespaces/ns-7/workspaces');

    await waitFor(() => expect(useSessionStore.getState().currentNamespaceId).toBe('ns-7'));
  });
});
