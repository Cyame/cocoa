import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchNamespaces, type NamespaceWithStats } from '@/lib/api/namespaces';
import { fetchOrganization, fetchOrganizationMembers } from '@/lib/api/organizations';
import type { Organization, OrgMember } from '@/lib/types';
import DashboardPage from '@/pages/DashboardPage';
import { useSessionStore } from '@/stores/session';

vi.mock('@/lib/api/namespaces', () => ({ fetchNamespaces: vi.fn() }));

vi.mock('@/lib/api/organizations', () => ({
  fetchOrganization: vi.fn(),
  fetchOrganizationMembers: vi.fn(),
}));

const mockedFetchNamespaces = vi.mocked(fetchNamespaces);
const mockedFetchOrganization = vi.mocked(fetchOrganization);
const mockedFetchMembers = vi.mocked(fetchOrganizationMembers);

const org: Organization = {
  id: 'org-1',
  slug: 'cocoa',
  name: 'Cocoa World',
  description: null,
  system_hub_provider_id: null,
  system_hub_model: null,
  cerebellum_default_provider_id: null,
  cerebellum_default_model: null,
  use_proxy: false,
  proxy_host: null,
  proxy_port: null,
  proxy_username: null,
  proxy_password: null,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: null,
};

const namespace1: NamespaceWithStats = {
  id: 'ns-1',
  org_id: 'org-1',
  slug: 'default',
  name: 'Default namespace',
  description: null,
  tags: null,
  workspace_count: 2,
  entity_count: 3,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

const member1: OrgMember = {
  id: 'contract-1',
  user: { id: 'u-1', username: 'alice', email: 'alice@example.com', nickname: 'Alice' },
  atoms: [{ id: 'g-1', slug: 'can_manage_org_members', name: 'can_manage_org_members' }],
  created_at: '2026-08-03T00:00:00Z',
};

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={['/orgs/org-1']}>
      <Routes>
        <Route path="/orgs/:orgId" element={<DashboardPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockedFetchNamespaces.mockReset();
  mockedFetchOrganization.mockReset();
  mockedFetchMembers.mockReset();
  useSessionStore.setState({
    token: 'jwt',
    user: null,
    currentOrgId: 'org-1',
    currentNamespaceId: null,
  });
});

describe('DashboardPage', () => {
  it('renders the org name/slug header, stats, quick actions and recent namespaces', async () => {
    mockedFetchOrganization.mockResolvedValue(org);
    mockedFetchNamespaces.mockResolvedValue({
      items: [namespace1],
      offset: 0,
      limit: 50,
      total: 1,
    });
    mockedFetchMembers.mockResolvedValue({ items: [member1] });
    renderDashboard();

    expect(
      await screen.findByRole('heading', { name: 'Cocoa World', level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByText('cocoa')).toBeInTheDocument();

    expect(screen.getByTestId('dashboard-stats-ns')).toHaveTextContent('1');
    expect(screen.getByTestId('dashboard-stats-members')).toHaveTextContent('1');

    expect(screen.getByTestId('dashboard-cta-namespace')).toHaveAttribute(
      'href',
      '/orgs/org-1/namespaces',
    );
    expect(screen.getByTestId('dashboard-cta-members')).toHaveAttribute(
      'href',
      '/orgs/org-1/members',
    );
    expect(screen.getByTestId('dashboard-recent-default')).toHaveAttribute(
      'href',
      '/orgs/org-1/namespaces/ns-1',
    );

    expect(screen.queryByText('No namespaces yet')).not.toBeInTheDocument();
    expect(screen.queryByText('No members yet')).not.toBeInTheDocument();
  });

  it('renders empty-state CTAs when the org has no namespaces or members', async () => {
    mockedFetchOrganization.mockResolvedValue(org);
    mockedFetchNamespaces.mockResolvedValue({ items: [], offset: 0, limit: 50, total: 0 });
    mockedFetchMembers.mockResolvedValue({ items: [] });
    renderDashboard();

    expect(await screen.findByText('No namespaces yet')).toBeInTheDocument();
    expect(screen.getByText('No members yet')).toBeInTheDocument();
    expect(screen.getByTestId('dashboard-stats-ns')).toHaveTextContent('0');
    expect(screen.getByTestId('dashboard-stats-members')).toHaveTextContent('0');
    expect(screen.queryByTestId('dashboard-recent-default')).not.toBeInTheDocument();
  });
});
