import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '@/lib/api';
import DebugPage from '@/pages/DebugPage';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

type EventFixture = {
  readonly id: string;
  readonly type: string;
  readonly actor_type: string;
  readonly actor_id: string | null;
  readonly resource_type: string | null;
  readonly resource_id: string | null;
  readonly payload: Record<string, unknown>;
  readonly request_id: string | null;
  readonly created_at: string;
};

const EVENT_1: EventFixture = {
  id: 'evt-1',
  type: 'harness.loop_started',
  actor_type: 'instance',
  actor_id: 'instance-1',
  resource_type: 'instance',
  resource_id: 'instance-1',
  payload: { loop_status: 'running', continuation_count: 0 },
  request_id: 'req-1',
  created_at: '2026-07-27T10:00:00Z',
};

const EVENT_2: EventFixture = {
  id: 'evt-2',
  type: 'harness.loop_paused',
  actor_type: 'supervisor',
  actor_id: 'user-1',
  resource_type: 'instance',
  resource_id: 'instance-2',
  payload: { reason: 'operator_interrupt' },
  request_id: 'req-2',
  created_at: '2026-07-27T10:01:00Z',
};

const EVENT_PAGE = {
  items: [EVENT_1, EVENT_2],
  next_cursor: null,
  total: 2,
};

function renderDebug() {
  return render(
    <MemoryRouter initialEntries={['/debug']}>
      <Routes>
        <Route path="/debug" element={<DebugPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function readBlobText(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve(reader.result as string);
    };
    reader.onerror = () => {
      reject(reader.error);
    };
    reader.readAsText(blob);
  });
}

beforeEach(() => {
  mockedApi.mockReset();
  mockedApi.mockResolvedValue(EVENT_PAGE);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('DebugPage', () => {
  it('renders event rows fetched from the events endpoint', async () => {
    renderDebug();

    expect(await screen.findByText('harness.loop_started')).toBeInTheDocument();
    expect(screen.getByText('harness.loop_paused')).toBeInTheDocument();
    expect(screen.getByText('instance-1')).toBeInTheDocument();
    expect(screen.getByText('user-1')).toBeInTheDocument();
    expect(screen.getByText('supervisor')).toBeInTheDocument();
    expect(screen.getByText('instance:instance-1')).toBeInTheDocument();
    expect(screen.getByText('instance:instance-2')).toBeInTheDocument();
    expect(mockedApi).toHaveBeenCalledWith(
      expect.stringMatching(/^\/events\?.*type_prefix=harness\./),
    );
  });

  it('refetches with the new filter params when Apply is clicked', async () => {
    renderDebug();
    await screen.findByText('harness.loop_started');

    mockedApi.mockClear();

    const typePrefixInput = screen.getByLabelText('Filter by type prefix');
    fireEvent.change(typePrefixInput, { target: { value: 'messaging.' } });

    const resourceTypeSelect = screen.getByLabelText('Filter by resource type');
    fireEvent.change(resourceTypeSelect, { target: { value: 'message' } });

    const requestIdInput = screen.getByLabelText('Filter by request id');
    fireEvent.change(requestIdInput, { target: { value: 'req-abc' } });

    fireEvent.click(screen.getByRole('button', { name: /apply/i }));

    await waitFor(() => {
      expect(mockedApi).toHaveBeenCalledTimes(1);
    });

    const callPath = mockedApi.mock.calls[0]?.[0] ?? '';
    expect(callPath).toContain('type_prefix=messaging.');
    expect(callPath).toContain('resource_type=message');
    expect(callPath).toContain('request_id=req-abc');
    expect(callPath).not.toContain('resource_id=');
    expect(callPath).not.toContain('since=');
    expect(callPath).not.toContain('until=');
  });

  it('exports the current event list as a JSON download', async () => {
    const createObjectURLSpy = vi.fn().mockReturnValue('blob:cocoa-events');
    const revokeObjectURLSpy = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', {
      value: createObjectURLSpy,
      configurable: true,
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      value: revokeObjectURLSpy,
      configurable: true,
    });
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(function noop(this: HTMLAnchorElement) {});

    renderDebug();
    await screen.findByText('harness.loop_started');

    fireEvent.click(screen.getByRole('button', { name: /export/i }));

    expect(createObjectURLSpy).toHaveBeenCalledTimes(1);
    const blob = createObjectURLSpy.mock.calls[0]?.[0];
    expect(blob).toBeInstanceOf(Blob);
    expect(clickSpy).toHaveBeenCalledTimes(1);

    const blobText = await readBlobText(blob as Blob);
    const parsed = JSON.parse(blobText);
    expect(parsed).toEqual([EVENT_1, EVENT_2]);

    const anchor = clickSpy.mock.instances[0] as unknown as HTMLAnchorElement | undefined;
    expect(anchor?.download).toMatch(/^cocoa-events-.*\.json$/);

    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:cocoa-events');
  });

  it('polls the events endpoint every 5 seconds', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    renderDebug();

    await waitFor(() => {
      expect(mockedApi).toHaveBeenCalledTimes(1);
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    expect(mockedApi).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
    expect(mockedApi).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(mockedApi).toHaveBeenCalledTimes(3);
  });

  it('surfaces an error message when the API rejects with a non-401 error', async () => {
    mockedApi.mockRejectedValue(new ApiError(500, { message: 'Backend offline' }));

    renderDebug();

    expect(await screen.findByRole('alert')).toHaveTextContent('Backend offline');
  });
});
