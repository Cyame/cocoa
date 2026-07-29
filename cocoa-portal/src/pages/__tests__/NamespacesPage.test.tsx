import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '@/lib/api';
import NamespacesPage from '@/pages/NamespacesPage';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

function renderNamespacesPage() {
  return render(
    <MemoryRouter initialEntries={['/namespaces?tab=workspace']}>
      <Routes>
        <Route path="/namespaces" element={<NamespacesPage />} />
        <Route path="/workspaces/:id" element={<p>Workspace IDE destination</p>} />
        <Route path="/login" element={<p>Login destination</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockedApi.mockReset();
});

describe('NamespacesPage', () => {
  it('renders workspace cards with membership and instance counts', async () => {
    mockedApi.mockImplementation((path) => {
      if (path === '/namespaces?limit=50&offset=0') {
        return Promise.resolve({
          items: [
            {
              id: 'ns-1',
              org_id: 'org-1',
              slug: 'default',
              name: 'Default namespace',
              description: null,
              tags: null,
              workspace_count: 1,
              entity_count: 0,
              created_at: '2026-07-01T00:00:00Z',
              updated_at: '2026-07-01T00:00:00Z',
            },
          ],
          offset: 0,
          limit: 50,
          total: 1,
        });
      }
      if (path === '/workspaces?limit=50&offset=0') {
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
      if (path === '/messaging/memberships?workspace_id=ws-1') {
        return Promise.resolve({ items: [{ id: 'member-1' }, { id: 'member-2' }], total: 2 });
      }
      return Promise.resolve({ items: [{ id: 'instance-1' }], total: 1 });
    });

    renderNamespacesPage();

    expect(await screen.findByRole('heading', { name: 'Research Lab' })).toBeInTheDocument();
    expect(screen.getByText('research-lab')).toBeInTheDocument();
    expect(screen.getByText('2 members')).toBeInTheDocument();
    expect(screen.getByText('1 instances')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('link', { name: /Research Lab/ }));
    expect(await screen.findByText('Workspace IDE destination')).toBeInTheDocument();
  });

  it('renders an empty state when there are no workspaces', async () => {
    mockedApi.mockImplementation((path) => {
      if (path === '/namespaces?limit=50&offset=0') {
        return Promise.resolve({ items: [], offset: 0, limit: 50, total: 0 });
      }
      return Promise.resolve({ items: [], offset: 0, limit: 50, total: 0 });
    });
    renderNamespacesPage();

    expect(await screen.findByText('No workspaces yet')).toBeInTheDocument();
  });

  it('redirects to login after a 401 response', async () => {
    mockedApi.mockRejectedValue(new ApiError(401, { message: 'Session expired' }));
    renderNamespacesPage();

    await waitFor(() => expect(screen.getByText('Login destination')).toBeInTheDocument());
  });
});
