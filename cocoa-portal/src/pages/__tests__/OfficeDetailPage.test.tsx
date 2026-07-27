import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import OfficeDetailPage from '@/pages/OfficeDetailPage';
import { useSelectedStore } from '@/stores/selected';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

function renderOfficeDetail() {
  return render(
    <MemoryRouter initialEntries={['/offices/office-1']}>
      <Routes>
        <Route path="/offices/:id" element={<OfficeDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockedApi.mockReset();
  useSelectedStore.setState({ officeId: null, instanceId: null, interactionMode: 'select' });
  mockedApi.mockImplementation((path) => {
    if (path === '/offices/office-1') {
      return Promise.resolve({
        id: 'office-1',
        name: 'Research Lab',
        slug: 'research-lab',
        blackboard_ref: null,
        created_at: '2026-07-01T00:00:00Z',
        updated_at: '2026-07-01T00:00:00Z',
      });
    }
    if (path === '/messaging/memberships?office_id=office-1') {
      return Promise.resolve({
        items: [
          {
            id: 'membership-1',
            office_id: 'office-1',
            user_id: 'user-1',
            instance_id: null,
            posx: 0,
            posy: 0,
            role: 'owner',
            permissions: null,
            created_at: '2026-07-01T00:00:00Z',
            updated_at: '2026-07-01T00:00:00Z',
          },
        ],
        total: 1,
      });
    }
    if (path === '/instances?office_id=office-1') {
      return Promise.resolve({
        items: [
          {
            id: 'instance-1',
            employee_id: 'employee-1',
            office_id: 'office-1',
            workspace_path: '/workspace/researcher',
            status: 'running',
            runtime_config: null,
            created_at: '2026-07-01T00:00:00Z',
            updated_at: '2026-07-01T00:00:00Z',
          },
        ],
        total: 1,
      });
    }
    return Promise.resolve({
      id: 'blackboard-1',
      office_id: 'office-1',
      content: 'Coordinate the quarterly research sprint.',
      manual_notes: 'Review findings every Friday.',
      created_at: '2026-07-01T00:00:00Z',
    });
  });
});

describe('OfficeDetailPage', () => {
  it('selects the office and renders employee memberships by default', async () => {
    renderOfficeDetail();

    expect(await screen.findByRole('heading', { name: 'Research Lab' })).toBeInTheDocument();
    expect(screen.getByText('user-1')).toBeInTheDocument();
    expect(useSelectedStore.getState().officeId).toBe('office-1');
  });

  it('switches to instances and renders instance content', async () => {
    renderOfficeDetail();
    await screen.findByRole('heading', { name: 'Research Lab' });

    fireEvent.click(screen.getByRole('tab', { name: 'Instances' }));

    expect(await screen.findByText('employee-1')).toBeInTheDocument();
    expect(screen.getByText('running')).toBeInTheDocument();
    expect(mockedApi).toHaveBeenCalledWith('/instances?office_id=office-1');
  });

  it('switches to blackboard and renders its summary', async () => {
    renderOfficeDetail();
    await screen.findByRole('heading', { name: 'Research Lab' });

    fireEvent.click(screen.getByRole('tab', { name: 'Blackboard' }));

    expect(
      await screen.findByText('Coordinate the quarterly research sprint.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Review findings every Friday.')).toBeInTheDocument();
    expect(mockedApi).toHaveBeenCalledWith('/blackboards?office_id=office-1');
  });
});
