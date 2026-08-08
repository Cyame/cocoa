import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import NamespacesListPage from '@/pages/NamespacesListPage';
import { useSessionStore } from '@/stores/session';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

const NAMESPACE_ROW = {
  id: 'ns-1',
  org_id: 'org-1',
  slug: 'default',
  name: 'Default namespace',
  description: 'Primary scenario',
  tags: null,
  workspace_count: 1,
  entity_count: 0,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/orgs/org-1/namespaces']}>
      <Routes>
        <Route path="/orgs/:orgId/namespaces" element={<NamespacesListPage />} />
        <Route
          path="/orgs/:orgId/namespaces/:nsId"
          element={<p>Namespace overview destination</p>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockedApi.mockReset();
  useSessionStore.setState({
    token: 'jwt',
    user: {
      user_id: 'user-1',
      username: 'operator',
      identity: 'org',
      is_super_admin: false,
      token: 'jwt',
    },
    currentOrgId: 'org-1',
    currentNamespaceId: null,
  });
});

describe('NamespacesListPage', () => {
  it('renders the org-scoped namespace table and navigates on row click', async () => {
    mockedApi.mockResolvedValue({
      items: [NAMESPACE_ROW],
      offset: 0,
      limit: 50,
      total: 1,
    });

    renderPage();

    expect(await screen.findByText('Default namespace')).toBeInTheDocument();
    expect(screen.getByText('default')).toBeInTheDocument();
    expect(screen.getByText('Primary scenario')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Default namespace'));
    expect(await screen.findByText('Namespace overview destination')).toBeInTheDocument();
  });

  it('renders an empty state when no namespaces exist', async () => {
    mockedApi.mockResolvedValue({ items: [], offset: 0, limit: 50, total: 0 });
    renderPage();

    await waitFor(() => expect(screen.getByText('No regions yet')).toBeInTheDocument());
  });
});
