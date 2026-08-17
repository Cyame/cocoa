import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '@/lib/api';
import NamespaceWorkspacesPage from '@/pages/NamespaceWorkspacesPage';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/orgs/org-1/namespaces/ns-1/workspaces']}>
      <Routes>
        <Route
          path="/orgs/:orgId/namespaces/:nsId/workspaces"
          element={<NamespaceWorkspacesPage />}
        />
        <Route path="/orgs/:orgId/workspaces/:id" element={<p>Workspace IDE destination</p>} />
        <Route path="/login" element={<p>Login destination</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockedApi.mockReset();
});

describe('NamespaceWorkspacesPage', () => {
  it('renders namespace-scoped workspace cards with membership and instance counts', async () => {
    mockedApi.mockImplementation((path) => {
      if (path === '/workspaces?limit=50&offset=0&namespace_id=ns-1') {
        return Promise.resolve({
          items: [
            {
              id: 'ws-1',
              namespace_id: 'ns-1',
              name: 'Research Lab',
              slug: 'research-lab',
              created_at: '2026-07-01T00:00:00Z',
              updated_at: '2026-07-01T00:00:00Z',
            },
          ],
          offset: 0,
          limit: 50,
          total: 1,
        });
      }
      if (
        typeof path === 'string' &&
        path.startsWith('/messaging/memberships?') &&
        path.includes('workspace_id=ws-1') &&
        path.includes('kind=user')
      ) {
        return Promise.resolve({ items: [{ id: 'member-1' }, { id: 'member-2' }], total: 2 });
      }
      return Promise.resolve({ items: [{ id: 'instance-1' }], total: 1 });
    });

    renderPage();

    expect(await screen.findByRole('heading', { name: 'Research Lab' })).toBeInTheDocument();
    expect(screen.getByText('research-lab')).toBeInTheDocument();
    expect(screen.getByText('2 Sapiens')).toBeInTheDocument();
    expect(screen.getByText('1 Creatures')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('link', { name: /Research Lab/ }));
    expect(await screen.findByText('Workspace IDE destination')).toBeInTheDocument();
  });

  it('renders an empty state when there are no workspaces', async () => {
    mockedApi.mockResolvedValue({ items: [], offset: 0, limit: 50, total: 0 });
    renderPage();

    expect(await screen.findByText('No habitats yet')).toBeInTheDocument();
  });

  it('redirects to login after a 401 response', async () => {
    mockedApi.mockRejectedValue(new ApiError(401, { message: 'Session expired' }));
    renderPage();

    await waitFor(() => expect(screen.getByText('Login destination')).toBeInTheDocument());
  });
});
