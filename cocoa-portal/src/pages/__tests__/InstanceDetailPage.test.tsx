import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '@/lib/api';
import InstanceDetailPage from '@/pages/InstanceDetailPage';
import { useSelectedStore } from '@/stores/selected';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const STATUS_RUNNING = {
  instance_id: 'instance-1',
  loop_status: 'running',
  continuation_count: 3,
  total_token_estimate: 12345,
  last_checkpoint_at: '2026-07-27T10:00:00Z',
  breaker_config: {
    max_continuations: 20,
    max_wall_clock_seconds: 3600,
    max_token_estimate: 100000,
    idle_timeout_seconds: 300,
  },
};

const STATUS_INTERRUPTED = { ...STATUS_RUNNING, loop_status: 'interrupted' };

const SNAPSHOT_RESPONSE = {
  boulder_snapshot: { phase: 'explore', tasks: ['read_file', 'grep'] },
  continuation_count: 3,
  captured_at: '2026-07-27T10:05:00Z',
};

const EVENT_FIXTURE = {
  id: 'evt-1',
  type: 'harness.interrupt',
  actor_type: 'user',
  actor_id: 'user-1',
  resource_type: 'instance',
  resource_id: 'instance-1',
  payload: { reason: 'operator_stop' },
  request_id: null,
  created_at: '2026-07-27T10:00:00Z',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type EndpointResponse = unknown;

function setupMockApi(options?: {
  readonly status?: unknown;
  readonly interruptStatus?: unknown;
  readonly snapshot?: unknown;
  readonly events?: readonly unknown[];
}) {
  const status = options?.status ?? STATUS_RUNNING;
  const interruptStatus = options?.interruptStatus ?? STATUS_INTERRUPTED;
  const snapshot = options?.snapshot ?? SNAPSHOT_RESPONSE;
  const events = options?.events ?? [EVENT_FIXTURE];

  mockedApi.mockImplementation((path: string, init?: RequestInit): Promise<EndpointResponse> => {
    if (path === '/instances/instance-1/status') {
      return Promise.resolve(status);
    }
    if (path === '/instances/instance-1/interrupt' && init?.method === 'POST') {
      return Promise.resolve(interruptStatus);
    }
    if (path === '/instances/instance-1/pause' && init?.method === 'POST') {
      return Promise.resolve({ ...status, loop_status: 'paused' });
    }
    if (path === '/instances/instance-1/resume' && init?.method === 'POST') {
      return Promise.resolve({ ...status, loop_status: 'running' });
    }
    if (path === '/instances/instance-1/snapshot' && init?.method === 'POST') {
      return Promise.resolve(snapshot);
    }
    if (path.startsWith('/events?')) {
      return Promise.resolve({ items: events, next_cursor: null, total: events.length });
    }
    return Promise.reject(new Error(`Unmocked path: ${path}`));
  });
}

function renderInstanceDetail() {
  return render(
    <MemoryRouter initialEntries={['/offices/office-1/instances/instance-1']}>
      <Routes>
        <Route path="/offices/:id/instances/:iid" element={<InstanceDetailPage />} />
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

describe('InstanceDetailPage', () => {
  it('renders the status bar with loop_status, continuations, checkpoint, and breaker config from the API', async () => {
    setupMockApi();

    renderInstanceDetail();

    // Loop status badge
    const badge = await screen.findByTestId('instance-loop-status-badge');
    expect(badge).toHaveTextContent('running');

    // Continuation count
    expect(screen.getByTestId('instance-continuation-count')).toHaveTextContent('3');

    // Last checkpoint
    expect(screen.getByTestId('instance-last-checkpoint')).toHaveTextContent('2026-07-27T10:00:00Z');

    // Breaker config renders the 4 thresholds
    const breaker = screen.getByTestId('instance-breaker-config');
    expect(breaker).toHaveTextContent('20');
    expect(breaker).toHaveTextContent('3600');
    expect(breaker).toHaveTextContent('100000');
    expect(breaker).toHaveTextContent('300');

    // Status endpoint was hit on mount
    expect(mockedApi).toHaveBeenCalledWith('/instances/instance-1/status');
  });

  it('POSTs to /interrupt and refetches status when the Interrupt button is clicked', async () => {
    setupMockApi();

    renderInstanceDetail();

    await screen.findByTestId('instance-loop-status-badge');

    fireEvent.click(screen.getByTestId('instance-control-interrupt'));

    // POST /interrupt fired
    await waitFor(() => {
      expect(mockedApi).toHaveBeenCalledWith('/instances/instance-1/interrupt', { method: 'POST' });
    });

    // Status badge updates to the interrupted state returned by the POST
    await waitFor(() => {
      expect(screen.getByTestId('instance-loop-status-badge')).toHaveTextContent('interrupted');
    });

    // Toast feedback
    expect(screen.getByTestId('instance-toast')).toHaveTextContent('Interrupt sent');
  });

  it('opens the snapshot modal with pretty-printed JSON when the Snapshot button is clicked', async () => {
    setupMockApi();

    renderInstanceDetail();

    await screen.findByTestId('instance-loop-status-badge');

    expect(screen.queryByTestId('instance-snapshot-modal')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('instance-control-snapshot'));

    // POST /snapshot fired
    await waitFor(() => {
      expect(mockedApi).toHaveBeenCalledWith('/instances/instance-1/snapshot', { method: 'POST' });
    });

    // Modal opens
    const modal = await screen.findByTestId('instance-snapshot-modal');
    expect(modal).toBeInTheDocument();

    // Pretty-printed JSON renders with 2-space indentation
    const json = screen.getByTestId('instance-snapshot-json');
    expect(json.textContent).toContain('"phase": "explore"');
    expect(json.textContent).toContain('"tasks": [');
    expect(json.textContent).toContain('"read_file"');

    // Copy button is present
    expect(screen.getByTestId('instance-snapshot-copy')).toBeInTheDocument();
  });

  it('surfaces an error banner when the status API rejects with a non-401 error', async () => {
    mockedApi.mockImplementation((path: string) => {
      if (path === '/instances/instance-1/status') {
        return Promise.reject(new ApiError(500, { message: 'Supervisor offline' }));
      }
      if (path.startsWith('/events?')) {
        return Promise.resolve({ items: [], next_cursor: null, total: 0 });
      }
      return Promise.reject(new Error(`Unmocked path: ${path}`));
    });

    renderInstanceDetail();

    expect(await screen.findByRole('alert')).toHaveTextContent('Supervisor offline');
  });
});
