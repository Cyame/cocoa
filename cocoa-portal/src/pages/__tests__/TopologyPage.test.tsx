import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '@/lib/api';
import TopologyPage from '@/pages/TopologyPage';
import { useSelectedStore } from '@/stores/selected';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

const MEMBERSHIP_INSTANCE: {
  id: string;
  office_id: string;
  user_id: null;
  instance_id: string;
  posx: number;
  posy: number;
  role: 'editor';
  permissions: null;
  created_at: string;
  updated_at: string;
} = {
  id: 'membership-1',
  office_id: 'office-1',
  user_id: null,
  instance_id: 'instance-1',
  posx: 200,
  posy: 100,
  role: 'editor',
  permissions: null,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

const MEMBERSHIP_USER: {
  id: string;
  office_id: string;
  user_id: string;
  instance_id: null;
  posx: number;
  posy: number;
  role: 'owner';
  permissions: null;
  created_at: string;
  updated_at: string;
} = {
  id: 'membership-2',
  office_id: 'office-1',
  user_id: 'user-1',
  instance_id: null,
  posx: -200,
  posy: -100,
  role: 'owner',
  permissions: null,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

const CORRIDOR_EDGE: {
  id: string;
  office_id: string;
  from_membership_id: string;
  to_membership_id: string;
  from_corridor_node_id: null;
  to_corridor_node_id: null;
  is_active: boolean;
} = {
  id: 'corridor-1',
  office_id: 'office-1',
  from_membership_id: 'membership-1',
  to_membership_id: 'membership-2',
  from_corridor_node_id: null,
  to_corridor_node_id: null,
  is_active: true,
};

const CORRIDOR_NODE_EDGE: {
  id: string;
  office_id: string;
  from_membership_id: null;
  to_membership_id: string;
  from_corridor_node_id: string;
  to_corridor_node_id: null;
  is_active: boolean;
} = {
  id: 'corridor-2',
  office_id: 'office-1',
  from_membership_id: null,
  to_membership_id: 'membership-1',
  from_corridor_node_id: 'corridor-node-1',
  to_corridor_node_id: null,
  is_active: true,
};

const CORRIDOR_NODE: {
  id: string;
  office_id: string;
  posx: number;
  posy: number;
  display_name: string;
  glow_color: string | null;
  status: 'active';
  created_by: string | null;
  created_at: string;
  updated_at: string;
} = {
  id: 'corridor-node-1',
  office_id: 'office-1',
  posx: 0,
  posy: 200,
  display_name: 'Hub',
  glow_color: '#3b82f6',
  status: 'active',
  created_by: 'user-1',
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

const LIVE_STATUS_ITEMS: readonly {
  membership_id: string;
  posx: number;
  posy: number;
  node_type: 'user' | 'instance';
  glow: { color: string; intensity: 'static' | 'weak' | 'low' | 'medium' | 'strong' };
}[] = [
  {
    membership_id: 'membership-1',
    posx: 200,
    posy: 100,
    node_type: 'instance',
    glow: { color: '#10b981', intensity: 'strong' },
  },
  {
    membership_id: 'membership-2',
    posx: -200,
    posy: -100,
    node_type: 'user',
    glow: { color: '#4f46e5', intensity: 'medium' },
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type EventOverride = {
  id: string;
  type: string;
  actor_type: string;
  actor_id: string | null;
  resource_type: string | null;
  resource_id: string | null;
  payload: Record<string, unknown>;
  request_id: string | null;
  created_at: string;
};

type CorridorFixture = typeof CORRIDOR_EDGE | typeof CORRIDOR_NODE_EDGE;
type EndpointResponse = unknown;

function setupMockApi(options?: {
  readonly corridors?: readonly CorridorFixture[];
  readonly corridorNodes?: readonly (typeof CORRIDOR_NODE)[];
  readonly liveStatus?: readonly (typeof LIVE_STATUS_ITEMS)[number][];
  readonly events?: readonly EventOverride[];
}) {
  const corridors = options?.corridors ?? [CORRIDOR_EDGE];
  const corridorNodes = options?.corridorNodes ?? [];
  const liveStatus = options?.liveStatus ?? LIVE_STATUS_ITEMS;
  const events = options?.events ?? [];

  mockedApi.mockImplementation((path: string): Promise<EndpointResponse> => {
    if (path.startsWith('/messaging/memberships?')) {
      return Promise.resolve({
        items: [MEMBERSHIP_INSTANCE, MEMBERSHIP_USER],
        total: 2,
      });
    }
    if (path.startsWith('/messaging/corridors?')) {
      return Promise.resolve({
        items: corridors,
        total: corridors.length,
      });
    }
    if (path.startsWith('/learning/corridor-nodes?')) {
      return Promise.resolve({
        items: corridorNodes,
        next_cursor: null,
        total: corridorNodes.length,
      });
    }
    if (path.includes('/live-status')) {
      return Promise.resolve(liveStatus);
    }
    if (path.startsWith('/events?')) {
      return Promise.resolve({
        items: events,
        next_cursor: null,
        total: events.length,
      });
    }
    return Promise.reject(new Error(`Unmocked path: ${path}`));
  });
}

function renderTopology() {
  return render(
    <MemoryRouter initialEntries={['/offices/office-1/topology']}>
      <Routes>
        <Route path="/offices/:id/topology" element={<TopologyPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockedApi.mockReset();
  useSelectedStore.setState({ officeId: null, instanceId: null, interactionMode: 'select' });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TopologyPage', () => {
  it('renders nodes fetched from the memberships and corridor-nodes endpoints', async () => {
    setupMockApi({ corridorNodes: [CORRIDOR_NODE] });

    renderTopology();

    // Wait for the static data fetch to complete (members + corridor nodes)
    await waitFor(() => {
      expect(screen.getByTestId('topology-node-membership-1')).toBeInTheDocument();
    });
    expect(screen.getByTestId('topology-node-membership-2')).toBeInTheDocument();
    expect(screen.getByTestId('topology-node-corridor-node-1')).toBeInTheDocument();

    // Instance node should render with the running glow color (green strong)
    const instanceNodeHalo = screen.getByTestId('topology-node-halo-membership-1');
    expect(instanceNodeHalo.getAttribute('stroke')).toBe('#10b981');
    expect(instanceNodeHalo.getAttribute('filter')).toBe('url(#topology-glow-blur)');

    // User node should pick up the user glow (indigo medium)
    const userNodeHalo = screen.getByTestId('topology-node-halo-membership-2');
    expect(userNodeHalo.getAttribute('stroke')).toBe('#4f46e5');

    // Tooltip combines label, role, and status
    const instanceTooltip = screen.getByTestId('topology-node-membership-1').querySelector('title');
    expect(instanceTooltip?.textContent).toBe('instance-1 | editor | strong');

    // Endpoint coverage
    expect(mockedApi).toHaveBeenCalledWith('/messaging/memberships?office_id=office-1');
    expect(mockedApi).toHaveBeenCalledWith('/messaging/corridors?office_id=office-1');
    expect(mockedApi).toHaveBeenCalledWith('/learning/corridor-nodes?office_id=office-1');
    expect(mockedApi).toHaveBeenCalledWith('/offices/office-1/live-status');
  });

  it('renders one line per resolved corridor with the default gray stroke', async () => {
    setupMockApi({
      corridors: [CORRIDOR_EDGE, CORRIDOR_NODE_EDGE],
      corridorNodes: [CORRIDOR_NODE],
    });

    renderTopology();

    await waitFor(() => {
      expect(screen.getByTestId('topology-corridor-line-corridor-1')).toBeInTheDocument();
    });

    const line1 = screen.getByTestId('topology-corridor-line-corridor-1');
    const line2 = screen.getByTestId('topology-corridor-line-corridor-2');

    expect(line1.getAttribute('stroke')).toBe('#94a3b8');
    expect(line1.getAttribute('stroke-width')).toBe('2');
    expect(line1.getAttribute('data-active')).toBe('false');

    expect(line2.getAttribute('stroke')).toBe('#94a3b8');
    expect(line2.getAttribute('stroke-width')).toBe('2');

    // Endpoints resolved: from (200, 100) -> to (-200, -100), and CN (0, 200) -> (200, 100)
    expect(line1.getAttribute('x1')).toBe('200');
    expect(line1.getAttribute('y1')).toBe('100');
    expect(line1.getAttribute('x2')).toBe('-200');
    expect(line1.getAttribute('y2')).toBe('-100');

    // No particles while corridors are inactive
    expect(screen.queryByTestId('topology-corridor-particle-corridor-1')).not.toBeInTheDocument();
  });

  it('updates the pan/zoom transform on wheel and drag interactions', async () => {
    setupMockApi();

    renderTopology();

    await waitFor(() => {
      expect(screen.getByTestId('topology-canvas-content')).toBeInTheDocument();
    });

    const content = screen.getByTestId('topology-canvas-content');
    const svg = screen.getByTestId('topology-canvas');

    // Initial transform: translate(0 0) scale(1)
    expect(content.getAttribute('transform')).toBe('translate(0 0) scale(1)');

    // Wheel zoom (negative deltaY -> zoom in, factor 1.1) clamps to [0.25, 4]
    fireEvent.wheel(svg, { deltaY: -100, clientX: 400, clientY: 300 });
    await waitFor(() => {
      expect(content.getAttribute('transform')).not.toBe('translate(0 0) scale(1)');
    });
    expect(content.getAttribute('transform')).toMatch(/scale\(1\.\d/);

    // Mouse drag pans the canvas
    fireEvent.mouseDown(svg, { clientX: 400, clientY: 300, button: 0 });
    await act(async () => {
      window.dispatchEvent(
        new MouseEvent('mousemove', { clientX: 500, clientY: 350, bubbles: true }),
      );
      window.dispatchEvent(
        new MouseEvent('mouseup', { clientX: 500, clientY: 350, bubbles: true }),
      );
    });

    await waitFor(() => {
      const transform = content.getAttribute('transform') ?? '';
      expect(transform).not.toBe('translate(0 0) scale(1)');
      expect(transform).toMatch(/translate\(-?\d/);
    });

    // Wheel zoom out should reduce the scale factor
    const transformBeforeZoomOut = content.getAttribute('transform') ?? '';
    const scaleMatch = transformBeforeZoomOut.match(/scale\(([\d.]+)\)/);
    const scaleValue = scaleMatch === null ? 1 : Number.parseFloat(scaleMatch[1] ?? '1');

    fireEvent.wheel(svg, { deltaY: 100, clientX: 400, clientY: 300 });
    await waitFor(() => {
      const next = content.getAttribute('transform') ?? '';
      const nextScale = next.match(/scale\(([\d.]+)\)/);
      const nextValue = nextScale === null ? 1 : Number.parseFloat(nextScale[1] ?? '1');
      expect(nextValue).toBeLessThan(scaleValue);
    });

    // Zoom clamps to MIN_ZOOM when zooming out repeatedly
    for (let i = 0; i < 30; i += 1) {
      fireEvent.wheel(svg, { deltaY: 100, clientX: 400, clientY: 300 });
    }
    await waitFor(() => {
      expect(content.getAttribute('transform')).toMatch(/scale\(0\.25\)/);
    });
  });

  it('animates a corridor line green with a particle when a messaging.message_sent event is polled', async () => {
    // Track the latest event response so the second poll can deliver one.
    let nextEvents: readonly EventOverride[] = [];
    const queueEvents = (events: readonly EventOverride[]) => {
      nextEvents = events;
    };

    mockedApi.mockImplementation((path: string): Promise<EndpointResponse> => {
      if (path.startsWith('/messaging/memberships?')) {
        return Promise.resolve({
          items: [MEMBERSHIP_INSTANCE, MEMBERSHIP_USER],
          total: 2,
        });
      }
      if (path.startsWith('/messaging/corridors?')) {
        return Promise.resolve({ items: [CORRIDOR_EDGE], total: 1 });
      }
      if (path.startsWith('/learning/corridor-nodes?')) {
        return Promise.resolve({ items: [], next_cursor: null, total: 0 });
      }
      if (path.includes('/live-status')) {
        return Promise.resolve(LIVE_STATUS_ITEMS);
      }
      if (path.startsWith('/events?')) {
        return Promise.resolve({
          items: nextEvents,
          next_cursor: null,
          total: nextEvents.length,
        });
      }
      return Promise.reject(new Error(`Unmocked path: ${path}`));
    });

    vi.useFakeTimers({ shouldAdvanceTime: true });

    renderTopology();

    await waitFor(() => {
      expect(screen.getByTestId('topology-corridor-line-corridor-1')).toBeInTheDocument();
    });

    const line = screen.getByTestId('topology-corridor-line-corridor-1');
    expect(line.getAttribute('stroke')).toBe('#94a3b8');
    expect(line.getAttribute('data-active')).toBe('false');

    // Queue a message_sent event for the second poll cycle.
    queueEvents([
      {
        id: 'evt-1',
        type: 'messaging.message_sent',
        actor_type: 'membership',
        actor_id: 'membership-1',
        resource_type: 'instance',
        resource_id: 'instance-1',
        payload: {
          corridor_id: 'corridor-1',
          office_id: 'office-1',
          from_membership_id: 'membership-1',
          to_membership_id: 'membership-2',
        },
        request_id: null,
        created_at: new Date().toISOString(),
      },
    ]);

    // Advance past the 2s polling interval so the queued events are fetched.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });

    await waitFor(() => {
      const live = screen.getByTestId('topology-corridor-line-corridor-1');
      expect(live.getAttribute('stroke')).toBe('#10b981');
      expect(live.getAttribute('stroke-width')).toBe('3');
      expect(live.getAttribute('data-active')).toBe('true');
    });
    expect(screen.getByTestId('topology-corridor-particle-corridor-1')).toBeInTheDocument();
    expect(screen.getByTestId('topology-corridor-line-corridor-1').getAttribute('x1')).toBe('200');
  });

  it('surfaces an error message when the API rejects with a non-401 error', async () => {
    mockedApi.mockRejectedValue(new ApiError(500, { message: 'Backend offline' }));

    renderTopology();

    expect(await screen.findByRole('alert')).toHaveTextContent('Backend offline');
  });

  it('creates a corridor via POST when connect mode clicks two nodes in sequence', async () => {
    setupMockApi();

    useSelectedStore.setState({ interactionMode: 'connect' });

    renderTopology();

    await waitFor(() => {
      expect(screen.getByTestId('topology-node-membership-1')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('topology-node-membership-1'));

    await waitFor(() => {
      expect(screen.getByTestId('topology-connect-hint')).toHaveTextContent(
        'Click the target node',
      );
    });

    const postSpy = vi.fn().mockResolvedValue({
      id: 'corridor-new',
      office_id: 'office-1',
      from_membership_id: 'membership-1',
      to_membership_id: 'membership-2',
      from_corridor_node_id: null,
      to_corridor_node_id: null,
      is_active: true,
    });
    mockedApi.mockImplementation((path: string, init?: RequestInit): Promise<EndpointResponse> => {
      if (path === '/messaging/corridors' && init?.method === 'POST') {
        return postSpy(path, init);
      }
      if (path.startsWith('/messaging/memberships?')) {
        return Promise.resolve({ items: [MEMBERSHIP_INSTANCE, MEMBERSHIP_USER], total: 2 });
      }
      if (path.startsWith('/messaging/corridors?')) {
        return Promise.resolve({ items: [CORRIDOR_EDGE], total: 1 });
      }
      if (path.startsWith('/learning/corridor-nodes?')) {
        return Promise.resolve({ items: [], next_cursor: null, total: 0 });
      }
      if (path.includes('/live-status')) {
        return Promise.resolve(LIVE_STATUS_ITEMS);
      }
      if (path.startsWith('/events?')) {
        return Promise.resolve({ items: [], next_cursor: null, total: 0 });
      }
      return Promise.reject(new Error(`Unmocked path: ${path}`));
    });

    fireEvent.click(screen.getByTestId('topology-node-membership-2'));

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledTimes(1);
    });

    const [calledPath, calledInit] = postSpy.mock.calls[0];
    expect(calledPath).toBe('/messaging/corridors');
    expect(calledInit?.method).toBe('POST');
    const body = JSON.parse(calledInit?.body as string);
    expect(body).toEqual({
      office_id: 'office-1',
      from_membership_id: 'membership-1',
      to_membership_id: 'membership-2',
      from_corridor_node_id: null,
      to_corridor_node_id: null,
    });
  });

  it('reverts the node position and shows an error when move drag PATCH returns 409', async () => {
    setupMockApi();

    useSelectedStore.setState({ interactionMode: 'move' });

    renderTopology();

    await waitFor(() => {
      expect(screen.getByTestId('topology-node-membership-1')).toBeInTheDocument();
    });

    const nodeGroup = screen.getByTestId('topology-node-membership-1');
    expect(nodeGroup.getAttribute('transform')).toBe('translate(200 100)');

    const patchSpy = vi
      .fn()
      .mockRejectedValue(
        new ApiError(409, { message: 'Position (300, 150) is already used in this office' }),
      );
    mockedApi.mockImplementation((path: string, init?: RequestInit): Promise<EndpointResponse> => {
      if (path.startsWith('/messaging/memberships/membership-1') && init?.method === 'PATCH') {
        return patchSpy(path, init);
      }
      if (path.startsWith('/messaging/memberships?')) {
        return Promise.resolve({ items: [MEMBERSHIP_INSTANCE, MEMBERSHIP_USER], total: 2 });
      }
      if (path.startsWith('/messaging/corridors?')) {
        return Promise.resolve({ items: [], total: 0 });
      }
      if (path.startsWith('/learning/corridor-nodes?')) {
        return Promise.resolve({ items: [], next_cursor: null, total: 0 });
      }
      if (path.includes('/live-status')) {
        return Promise.resolve(LIVE_STATUS_ITEMS);
      }
      if (path.startsWith('/events?')) {
        return Promise.resolve({ items: [], next_cursor: null, total: 0 });
      }
      return Promise.reject(new Error(`Unmocked path: ${path}`));
    });

    fireEvent.mouseDown(nodeGroup, { clientX: 250, clientY: 150, button: 0 });
    await act(async () => {
      window.dispatchEvent(
        new MouseEvent('mousemove', { clientX: 300, clientY: 200, bubbles: true }),
      );
    });
    await act(async () => {
      window.dispatchEvent(
        new MouseEvent('mouseup', { clientX: 300, clientY: 200, bubbles: true }),
      );
    });

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledTimes(1);
    });

    const [calledPath, calledInit] = patchSpy.mock.calls[0];
    expect(calledPath).toBe('/messaging/memberships/membership-1');
    expect(calledInit?.method).toBe('PATCH');
    const body = JSON.parse(calledInit?.body as string);
    expect(body.posx).toBeTypeOf('number');
    expect(body.posy).toBeTypeOf('number');

    await waitFor(() => {
      expect(screen.getByTestId('topology-action-error')).toHaveTextContent(
        /Position.*is already used/,
      );
    });

    await waitFor(() => {
      const reverted = screen.getByTestId('topology-node-membership-1');
      expect(reverted.getAttribute('transform')).toBe('translate(200 100)');
    });
  });
});
