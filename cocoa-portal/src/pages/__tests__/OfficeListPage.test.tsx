import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '@/lib/api';
import OfficeListPage from '@/pages/OfficeListPage';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

function renderOfficeList() {
  return render(
    <MemoryRouter initialEntries={['/offices']}>
      <Routes>
        <Route path="/offices" element={<OfficeListPage />} />
        <Route path="/offices/:id" element={<p>Office detail destination</p>} />
        <Route path="/login" element={<p>Login destination</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockedApi.mockReset();
});

describe('OfficeListPage', () => {
  it('renders office cards with membership and instance counts', async () => {
    mockedApi.mockImplementation((path) => {
      if (path === '/offices') {
        return Promise.resolve({
          items: [
            {
              id: 'office-1',
              name: 'Research Lab',
              slug: 'research-lab',
              blackboard_ref: null,
              created_at: '2026-07-01T00:00:00Z',
              updated_at: '2026-07-01T00:00:00Z',
            },
          ],
          offset: 0,
          limit: 50,
          total: 1,
        });
      }
      if (path === '/messaging/memberships?office_id=office-1') {
        return Promise.resolve({ items: [{ id: 'member-1' }, { id: 'member-2' }], total: 2 });
      }
      return Promise.resolve({ items: [{ id: 'instance-1' }], total: 1 });
    });

    renderOfficeList();

    expect(await screen.findByRole('heading', { name: 'Research Lab' })).toBeInTheDocument();
    expect(screen.getByText('research-lab')).toBeInTheDocument();
    expect(screen.getByText('2 members')).toBeInTheDocument();
    expect(screen.getByText('1 instance')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('link', { name: /Research Lab/ }));
    expect(await screen.findByText('Office detail destination')).toBeInTheDocument();
  });

  it('renders an empty state when there are no offices', async () => {
    mockedApi.mockResolvedValue({ items: [], offset: 0, limit: 50, total: 0 });
    renderOfficeList();

    expect(await screen.findByText('No offices available')).toBeInTheDocument();
  });

  it('redirects to login after a 401 response', async () => {
    mockedApi.mockRejectedValue(new ApiError(401, { message: 'Session expired' }));
    renderOfficeList();

    await waitFor(() => expect(screen.getByText('Login destination')).toBeInTheDocument());
  });
});
