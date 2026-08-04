import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '@/lib/api';
import TopologyPage from '@/pages/TopologyPage';
import { useSelectedStore } from '@/stores/selected';
import { useTabStore } from '@/stores/tabStore';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

const MEMBERSHIP_INSTANCE = {
  id: 'membership-1',
  workspace_id: 'ws-1',
  user_id: null,
  instance_id: 'instance-1',
  posx: 200,
  posy: 100,
  permissions: null,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

const MEMBERSHIP_USER = {
  id: 'membership-2',
  workspace_id: 'ws-1',
  user_id: 'user-1',
  instance_id: null,
  posx: -200,
  posy: -100,
  permissions: null,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

const PASSAGE_EDGE = {
  id: 'passage-1',
  workspace_id: 'ws-1',
  from_membership_id: 'membership-1',
  to_membership_id: 'membership-2',
  is_active: true,
  edge_meta: null,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

const LIVE_STATUS_ITEMS = [
  {
    membership_id: 'membership-1',
    posx: 200,
    posy: 100,
    node_type: 'instance' as const,
    glow: { color: '#10b981', intensity: 'strong' as const },
    outdated: true,
    active_hash: 'sha256:old',
  },
  {
    membership_id: 'membership-2',
    posx: -200,
    posy: -100,
    node_type: 'user' as const,
    glow: { color: '#4f46e5', intensity: 'medium' as const },
    outdated: false,
    active_hash: null,
  },
];

function setupMockApi(options?: {
  readonly passages?: readonly (typeof PASSAGE_EDGE)[];
  readonly liveStatus?: typeof LIVE_STATUS_ITEMS;
}) {
  let passages = options?.passages ?? [PASSAGE_EDGE];
  const liveStatus = options?.liveStatus ?? LIVE_STATUS_ITEMS;

  mockedApi.mockImplementation((path: string, init?: RequestInit) => {
    if (path.startsWith('/messaging/memberships?')) {
      return Promise.resolve({ items: [MEMBERSHIP_INSTANCE, MEMBERSHIP_USER], total: 2 });
    }
    if (path === '/messaging/passages' && init?.method === 'POST') {
      return Promise.resolve(PASSAGE_EDGE);
    }
    if (path === '/messaging/passages/passage-1' && init?.method === 'DELETE') {
      passages = [];
      return Promise.resolve(undefined);
    }
    if (path === '/instances/instance-1' && init?.method === 'DELETE') {
      return Promise.resolve(undefined);
    }
    if (path.startsWith('/messaging/passages?')) {
      return Promise.resolve({ items: passages, total: passages.length });
    }
    if (path.includes('/live-status')) {
      return Promise.resolve(liveStatus);
    }
    if (path.startsWith('/events?')) {
      return Promise.resolve({ items: [], next_cursor: null, total: 0 });
    }
    return Promise.reject(new Error(`Unmocked path: ${path}`));
  });
}

function renderTopology() {
  return render(
    <MemoryRouter initialEntries={['/workspaces/ws-1']}>
      <Routes>
        <Route path="/workspaces/:id" element={<TopologyPage embedded />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockedApi.mockReset();
  useSelectedStore.setState({
    workspaceId: null,
    officeId: null,
    instanceId: null,
    interactionMode: 'select',
  });
  useTabStore.setState({ tabs: [], activeTabId: 'topology' });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('TopologyPage', () => {
  it('renders membership nodes from workspace endpoints', async () => {
    setupMockApi();

    renderTopology();

    await waitFor(() => {
      expect(screen.getByTestId('topology-node-membership-1')).toBeInTheDocument();
    });
    expect(screen.getByTestId('topology-node-membership-2')).toBeInTheDocument();

    expect(mockedApi).toHaveBeenCalledWith('/messaging/memberships?workspace_id=ws-1');
    expect(mockedApi).toHaveBeenCalledWith('/messaging/passages?workspace_id=ws-1');
    expect(mockedApi).toHaveBeenCalledWith('/workspaces/ws-1/live-status');
  });

  it('renders passage lines between memberships', async () => {
    setupMockApi();

    renderTopology();

    await waitFor(() => {
      expect(screen.getByTestId('topology-passage-line-passage-1')).toBeInTheDocument();
    });

    const line = screen.getByTestId('topology-passage-line-passage-1');
    expect(line.getAttribute('stroke')).toBe('#94a3b8');
    expect(line.getAttribute('data-active')).toBe('false');
  });

  it('renders outdated overlay and opens instance tab on double click', async () => {
    setupMockApi();
    renderTopology();

    const node = await screen.findByTestId('topology-node-membership-1');
    expect(screen.getByTestId('topology-node-outdated-membership-1')).toBeInTheDocument();

    fireEvent.doubleClick(node);
    expect(useTabStore.getState().tabs).toEqual([
      { id: 'instance-instance-1', label: 'instance-1', instanceId: 'instance-1' },
    ]);
  });

  it('creates a passage when connecting two memberships', async () => {
    setupMockApi({ passages: [] });

    renderTopology();
    await screen.findByTestId('topology-node-membership-1');

    fireEvent.click(screen.getByTestId('topology-toolbar-connect'));
    fireEvent.click(screen.getByTestId('topology-node-membership-1'));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 350));
    });
    expect(screen.getByTestId('topology-connect-hint')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('topology-node-membership-2'));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 350));
    });

    await waitFor(() => {
      expect(mockedApi).toHaveBeenCalledWith(
        '/messaging/passages',
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  it('shows action error when passage creation fails', async () => {
    mockedApi.mockImplementation((path: string, init?: RequestInit) => {
      if (path === '/messaging/passages' && init?.method === 'POST') {
        return Promise.reject(new ApiError(409, { message: 'Edge exists' }));
      }
      if (path.startsWith('/messaging/memberships?')) {
        return Promise.resolve({ items: [MEMBERSHIP_INSTANCE, MEMBERSHIP_USER], total: 2 });
      }
      if (path.startsWith('/messaging/passages?')) {
        return Promise.resolve({ items: [], total: 0 });
      }
      if (path.includes('/live-status')) return Promise.resolve(LIVE_STATUS_ITEMS);
      if (path.startsWith('/events?')) {
        return Promise.resolve({ items: [], next_cursor: null, total: 0 });
      }
      return Promise.reject(new Error(`Unmocked: ${path}`));
    });

    renderTopology();
    await screen.findByTestId('topology-node-membership-1');
    fireEvent.click(screen.getByTestId('topology-toolbar-connect'));
    fireEvent.click(screen.getByTestId('topology-node-membership-1'));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 350));
    });
    fireEvent.click(screen.getByTestId('topology-node-membership-2'));
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 350));
    });

    expect(await screen.findByTestId('topology-action-error')).toBeInTheDocument();
  });

  it('selects a passage edge in select mode', async () => {
    setupMockApi();

    renderTopology();
    await screen.findByTestId('topology-passage-line-passage-1');

    fireEvent.click(screen.getByTestId('topology-passage-hit-passage-1'));

    const line = screen.getByTestId('topology-passage-line-passage-1');
    expect(line.getAttribute('data-selected')).toBe('true');
    expect(line.getAttribute('stroke')).toBe('#2563eb');
    expect(screen.getByTestId('topology-delete-selection')).toBeEnabled();
  });

  it('deletes the selected passage from the toolbar after confirmation', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    setupMockApi();

    renderTopology();
    await screen.findByTestId('topology-passage-hit-passage-1');

    fireEvent.click(screen.getByTestId('topology-passage-hit-passage-1'));
    fireEvent.click(screen.getByTestId('topology-delete-selection'));

    await waitFor(() => {
      expect(mockedApi).toHaveBeenCalledWith(
        '/messaging/passages/passage-1',
        expect.objectContaining({ method: 'DELETE' }),
      );
    });
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      expect(screen.queryByTestId('topology-passage-line-passage-1')).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId('topology-delete-selection')).toBeDisabled();
    });
  });

  it('deletes the selected passage with the Delete key', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    setupMockApi();

    renderTopology();
    await screen.findByTestId('topology-passage-hit-passage-1');
    fireEvent.click(screen.getByTestId('topology-passage-hit-passage-1'));

    fireEvent.keyDown(window, { key: 'Delete' });

    await waitFor(() => {
      expect(mockedApi).toHaveBeenCalledWith(
        '/messaging/passages/passage-1',
        expect.objectContaining({ method: 'DELETE' }),
      );
    });
    expect(confirmSpy).toHaveBeenCalledTimes(1);
  });

  it('deletes a node with the Delete key after confirmation', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    setupMockApi();

    renderTopology();
    const node = await screen.findByTestId('topology-node-membership-1');
    fireEvent.click(node);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 350));
    });
    expect(screen.getByTestId('topology-node-modal')).toBeInTheDocument();

    fireEvent.keyDown(window, { key: 'Delete' });

    await waitFor(() => {
      expect(mockedApi).toHaveBeenCalledWith(
        '/instances/instance-1',
        expect.objectContaining({ method: 'DELETE' }),
      );
    });
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      expect(screen.queryByTestId('topology-node-modal')).not.toBeInTheDocument();
    });
  });
});
