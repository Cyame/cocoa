import {
  Activity,
  AlertCircle,
  ArrowLeft,
  Camera,
  Copy,
  LoaderCircle,
  Pause,
  Play,
  Power,
  RefreshCw,
} from 'lucide-react';
import { type ReactElement, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';
import { ApiError, api } from '@/lib/api';
import type { BoulderSnapshot, Event, InstanceLoopState, LoopStatus } from '@/lib/types';
import { useSelectedStore } from '@/stores/selected';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type CursorPage<T> = {
  readonly items: readonly T[];
  readonly next_cursor: string | null;
  readonly total: number | null;
};

type Toast = {
  readonly kind: 'success' | 'error';
  readonly message: string;
};

type ControlId = 'interrupt' | 'pause' | 'resume' | 'status' | 'snapshot';

type ControlButton = {
  readonly id: ControlId;
  readonly label: string;
  readonly Icon: typeof Power;
  readonly method: 'POST' | 'GET';
  readonly path: 'interrupt' | 'pause' | 'resume' | 'status' | 'snapshot';
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_POLL_INTERVAL_MS = 2000;
const EVENT_POLL_INTERVAL_MS = 2000;
const TOAST_AUTO_DISMISS_MS = 3000;
const EVENT_LIMIT = 50;

type ReadonlyRecord<K extends string, V> = { readonly [key in K]: V };

// ---------------------------------------------------------------------------
// InstanceDetailPage
// ---------------------------------------------------------------------------

export default function InstanceDetailPage() {
  const { t } = useTranslation();
  const { id: officeId, iid: instanceId } = useParams<{ id: string; iid: string }>();
  const setOfficeId = useSelectedStore((state) => state.setOfficeId);
  const setInstanceId = useSelectedStore((state) => state.setInstanceId);

  const [status, setStatus] = useState<InstanceLoopState | null>(null);
  const [events, setEvents] = useState<readonly Event[]>([]);
  const [snapshot, setSnapshot] = useState<BoulderSnapshot | null>(null);
  const [isSnapshotOpen, setIsSnapshotOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [busyButton, setBusyButton] = useState<ControlId | null>(null);

  const STATUS_BADGE: ReadonlyRecord<LoopStatus, { label: string; className: string }> = useMemo(
    () => ({
      idle: {
        label: t('instance.statusIdle'),
        className: 'bg-yellow-50 text-yellow-800 border-yellow-200',
      },
      running: {
        label: t('instance.statusRunning'),
        className: 'bg-emerald-50 text-emerald-800 border-emerald-200',
      },
      paused: {
        label: t('instance.statusPaused'),
        className: 'bg-slate-100 text-slate-700 border-slate-200',
      },
      interrupted: {
        label: t('instance.statusInterrupted'),
        className: 'bg-orange-50 text-orange-800 border-orange-200',
      },
      completed: {
        label: t('instance.statusCompleted'),
        className: 'bg-blue-50 text-blue-800 border-blue-200',
      },
      failed: {
        label: t('instance.statusFailed'),
        className: 'bg-red-50 text-red-800 border-red-200',
      },
    }),
    [t],
  );

  const CONTROL_BUTTONS: ReadonlyArray<ControlButton> = useMemo(
    () => [
      {
        id: 'interrupt',
        label: t('instance.interrupt'),
        Icon: Power,
        method: 'POST',
        path: 'interrupt',
      },
      { id: 'pause', label: t('instance.pause'), Icon: Pause, method: 'POST', path: 'pause' },
      { id: 'resume', label: t('instance.resume'), Icon: Play, method: 'POST', path: 'resume' },
      { id: 'status', label: t('instance.status'), Icon: Activity, method: 'GET', path: 'status' },
      {
        id: 'snapshot',
        label: t('instance.snapshot'),
        Icon: Camera,
        method: 'POST',
        path: 'snapshot',
      },
    ],
    [t],
  );

  // Refs so the polling closures always read the latest instance id without
  // re-subscribing on every status update (which would reset the interval).
  const instanceIdRef = useRef<string | null>(instanceId ?? null);
  useEffect(() => {
    instanceIdRef.current = instanceId ?? null;
  }, [instanceId]);

  // Sync selection store (matches OfficeDetailPage pattern).
  useEffect(() => {
    if (officeId !== undefined) setOfficeId(officeId);
    if (instanceId !== undefined) setInstanceId(instanceId);
    return () => {
      setOfficeId(null);
      setInstanceId(null);
    };
  }, [officeId, instanceId, setOfficeId, setInstanceId]);

  const fetchStatus = useCallback(async (iid: string): Promise<InstanceLoopState> => {
    const data = await api<InstanceLoopState>(`/instances/${iid}/status`);
    setStatus(data);
    return data;
  }, []);

  const fetchEvents = useCallback(async (iid: string): Promise<readonly Event[]> => {
    const path = `/events?resource_type=instance&resource_id=${encodeURIComponent(iid)}&limit=${EVENT_LIMIT}`;
    const page = await api<CursorPage<Event>>(path);
    setEvents(page.items);
    return page.items;
  }, []);

  const refreshAll = useCallback(
    async (iid: string): Promise<void> => {
      await fetchStatus(iid);
      await fetchEvents(iid).catch(() => {});
    },
    [fetchStatus, fetchEvents],
  );

  // ---- Initial load ----
  useEffect(() => {
    if (instanceId === undefined) return;
    const iid = instanceId;
    let isActive = true;
    setIsLoading(true);
    setErrorMessage(null);

    async function load() {
      try {
        await refreshAll(iid);
      } catch (error) {
        if (!isActive) return;
        const message = error instanceof Error ? error.message : t('instance.loadStatusFailed');
        setErrorMessage(message);
      } finally {
        if (isActive) setIsLoading(false);
      }
    }

    void load();
    return () => {
      isActive = false;
    };
  }, [instanceId, refreshAll, t]);

  // ---- Status polling (every 2s, best-effort) ----
  useEffect(() => {
    if (instanceId === undefined) return;
    const iid = instanceId;
    let cancelled = false;
    let timerId: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      if (cancelled) return;
      try {
        await fetchStatus(iid);
      } catch {
        // Polling errors are best-effort; the initial-load banner already
        // surfaces persistent failures.
      } finally {
        if (!cancelled) timerId = setTimeout(poll, STATUS_POLL_INTERVAL_MS);
      }
    }

    timerId = setTimeout(poll, STATUS_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timerId !== null) clearTimeout(timerId);
    };
  }, [instanceId, fetchStatus]);

  // ---- Event polling (every 2s, best-effort) ----
  useEffect(() => {
    if (instanceId === undefined) return;
    const iid = instanceId;
    let cancelled = false;
    let timerId: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      if (cancelled) return;
      try {
        await fetchEvents(iid);
      } catch {
        // best-effort
      } finally {
        if (!cancelled) timerId = setTimeout(poll, EVENT_POLL_INTERVAL_MS);
      }
    }

    timerId = setTimeout(poll, EVENT_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timerId !== null) clearTimeout(timerId);
    };
  }, [instanceId, fetchEvents]);

  // ---- Toast auto-dismiss ----
  useEffect(() => {
    if (toast === null) return;
    const timerId = setTimeout(() => setToast(null), TOAST_AUTO_DISMISS_MS);
    return () => clearTimeout(timerId);
  }, [toast]);

  // ---- Control button handler ----
  const handleControl = useCallback(
    async (button: ControlButton) => {
      const iid = instanceIdRef.current;
      if (iid === null) return;
      setBusyButton(button.id);
      const verb =
        button.id === 'snapshot'
          ? t('instance.snapshotCaptured')
          : button.id === 'status'
            ? t('instance.statusRefreshed')
            : `${button.label} sent`;
      try {
        if (button.id === 'snapshot') {
          const snap = await api<BoulderSnapshot>(`/instances/${iid}/snapshot`, {
            method: 'POST',
          });
          setSnapshot(snap);
          setIsSnapshotOpen(true);
          setToast({ kind: 'success', message: verb });
        } else if (button.method === 'POST') {
          const next = await api<InstanceLoopState>(`/instances/${iid}/${button.path}`, {
            method: 'POST',
          });
          setStatus(next);
          setToast({ kind: 'success', message: verb });
        } else {
          await fetchStatus(iid);
          setToast({ kind: 'success', message: verb });
        }
        // Refresh events so the operator sees the audit trail immediately.
        await fetchEvents(iid).catch(() => {});
      } catch (error) {
        const message =
          error instanceof ApiError ? error.message : t('instance.controlRequestFailed');
        setToast({ kind: 'error', message });
      } finally {
        setBusyButton(null);
      }
    },
    [fetchStatus, fetchEvents, t],
  );

  const closeSnapshot = useCallback(() => {
    setIsSnapshotOpen(false);
  }, []);

  const copySnapshot = useCallback(async (): Promise<void> => {
    if (snapshot === null) return;
    const text = JSON.stringify(snapshot.boulder_snapshot, null, 2);
    try {
      await navigator.clipboard.writeText(text);
      setToast({ kind: 'success', message: t('instance.snapshotCopied') });
    } catch {
      setToast({ kind: 'error', message: t('instance.clipboardUnavailable') });
    }
  }, [snapshot, t]);

  // ---- Render: guards ----
  if (instanceId === undefined || officeId === undefined) {
    return (
      <section className="mx-auto w-full max-w-6xl p-6 lg:p-8">
        <p className="rounded-lg border border-dashed border-red-300 bg-red-50 px-6 py-12 text-center text-sm text-red-700">
          {t('instance.noInstance')}
        </p>
      </section>
    );
  }

  return (
    <section className="mx-auto w-full max-w-6xl p-6 lg:p-8" aria-labelledby="instance-title">
      <header className="mb-6">
        <Link
          to={`/offices/${officeId}`}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 transition-colors hover:text-slate-900"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          {t('instance.backToOffice')}
        </Link>
        <div className="mt-3 flex items-start gap-4">
          <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-slate-900 text-white">
            <Activity className="size-6" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="font-mono text-xs text-slate-500">{instanceId}</p>
            <h1
              id="instance-title"
              className="mt-1 truncate text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl"
            >
              Instance detail
            </h1>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Harness control panel. Status polls every 2 seconds.
            </p>
          </div>
        </div>
      </header>

      {toast !== null ? <ToastView toast={toast} /> : null}

      {errorMessage !== null ? (
        <div
          role="alert"
          className="mb-6 flex gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p>{errorMessage}</p>
        </div>
      ) : null}

      <StatusBar status={status} isLoading={isLoading} badgeMap={STATUS_BADGE} />

      <ControlToolbar
        buttons={CONTROL_BUTTONS}
        busyButton={busyButton}
        onControl={handleControl}
        disabled={isLoading && status === null}
      />

      <EventPanel events={events} isLoading={isLoading} />

      {isSnapshotOpen && snapshot !== null ? (
        <SnapshotModal snapshot={snapshot} onClose={closeSnapshot} onCopy={copySnapshot} />
      ) : null}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Sub-views
// ---------------------------------------------------------------------------

type StatusBarProps = {
  readonly status: InstanceLoopState | null;
  readonly isLoading: boolean;
  readonly badgeMap: ReadonlyRecord<LoopStatus, { label: string; className: string }>;
};

function StatusBar({ status, isLoading, badgeMap }: StatusBarProps): ReactElement {
  const breaker = status?.breaker_config;
  const badge = status !== null ? (badgeMap[status.loop_status] ?? null) : null;

  return (
    <section
      aria-label="Loop status"
      className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"
      data-testid="instance-status-bar"
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatusMetric
          label="Loop status"
          value={
            badge !== null ? (
              <span
                className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${badge.className}`}
                data-testid="instance-loop-status-badge"
              >
                {badge.label}
              </span>
            ) : (
              <Placeholder isLoading={isLoading} />
            )
          }
        />
        <StatusMetric
          label="Continuations"
          value={
            status !== null ? (
              <span
                className="font-mono text-lg text-slate-950"
                data-testid="instance-continuation-count"
              >
                {status.continuation_count}
              </span>
            ) : (
              <Placeholder isLoading={isLoading} />
            )
          }
        />
        <StatusMetric
          label="Last checkpoint"
          value={
            status !== null ? (
              <span
                className="font-mono text-sm text-slate-700"
                data-testid="instance-last-checkpoint"
              >
                {status.last_checkpoint_at ?? 'never'}
              </span>
            ) : (
              <Placeholder isLoading={isLoading} />
            )
          }
        />
        <StatusMetric
          label="Breaker config"
          value={
            breaker !== undefined ? (
              <dl
                className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-xs text-slate-700"
                data-testid="instance-breaker-config"
              >
                <BreakerRow label="max_cont" value={breaker.max_continuations} />
                <BreakerRow label="max_wall" value={breaker.max_wall_clock_seconds} />
                <BreakerRow label="max_token" value={breaker.max_token_estimate} />
                <BreakerRow label="idle_t" value={breaker.idle_timeout_seconds} />
              </dl>
            ) : (
              <Placeholder isLoading={isLoading} />
            )
          }
        />
      </div>
    </section>
  );
}

type StatusMetricProps = {
  readonly label: string;
  readonly value: ReactElement | ReactElement[] | string;
};

function StatusMetric({ label, value }: StatusMetricProps): ReactElement {
  return (
    <div className="min-w-0">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <div className="mt-2 min-w-0">{value}</div>
    </div>
  );
}

function BreakerRow({ label, value }: { label: string; value: unknown }): ReactElement {
  return (
    <>
      <dt className="text-slate-400">{label}</dt>
      <dd className="text-right tabular-nums">
        {value === undefined || value === null ? '-' : String(value)}
      </dd>
    </>
  );
}

function Placeholder({ isLoading }: { isLoading: boolean }): ReactElement {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-slate-400">
      {isLoading ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : null}
      {isLoading ? 'Loading' : 'Unavailable'}
    </span>
  );
}

type ControlToolbarProps = {
  readonly buttons: ReadonlyArray<ControlButton>;
  readonly busyButton: ControlId | null;
  readonly disabled: boolean;
  readonly onControl: (button: ControlButton) => void;
};

function ControlToolbar({
  buttons,
  busyButton,
  disabled,
  onControl,
}: ControlToolbarProps): ReactElement {
  return (
    <section
      aria-label="Harness controls"
      className="mb-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
    >
      <div className="flex flex-wrap gap-2" role="toolbar" aria-label="Instance control actions">
        {buttons.map((button) => {
          const { id, label, Icon } = button;
          const isBusy = busyButton === id;
          return (
            <button
              key={id}
              type="button"
              disabled={disabled || isBusy}
              onClick={() => onControl(button)}
              data-testid={`instance-control-${id}`}
              aria-label={label}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isBusy ? (
                <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <Icon className="size-4" aria-hidden="true" />
              )}
              {label}
            </button>
          );
        })}
      </div>
    </section>
  );
}

type EventPanelProps = {
  readonly events: readonly Event[];
  readonly isLoading: boolean;
};

function EventPanel({ events, isLoading }: EventPanelProps): ReactElement {
  return (
    <section
      aria-label="Instance events"
      className="rounded-xl border border-slate-200 bg-white shadow-sm"
    >
      <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Event stream</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            Latest {events.length} audit events for this instance.
          </p>
        </div>
        <span
          className="inline-flex items-center gap-1.5 text-xs text-slate-400"
          data-testid="instance-event-count"
        >
          <RefreshCw className="size-3.5" aria-hidden="true" />
          {events.length}
        </span>
      </header>
      <div className="max-h-96 overflow-y-auto">
        {isLoading && events.length === 0 ? (
          <div className="flex items-center justify-center gap-3 px-5 py-12 text-sm text-slate-500">
            <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
            Loading events
          </div>
        ) : events.length === 0 ? (
          <p className="px-5 py-12 text-center text-sm text-slate-500">No events recorded yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100" data-testid="instance-event-list">
            {events.map((event) => (
              <li key={event.id} className="px-5 py-3" data-testid={`instance-event-${event.id}`}>
                <div className="flex items-baseline justify-between gap-3">
                  <p className="truncate font-mono text-xs font-semibold text-slate-800">
                    {event.type}
                  </p>
                  <time className="shrink-0 font-mono text-xs text-slate-400">
                    {event.created_at}
                  </time>
                </div>
                <p className="mt-1 truncate font-mono text-xs text-slate-500">
                  actor={event.actor_type}/{event.actor_id ?? '-'}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

type SnapshotModalProps = {
  readonly snapshot: BoulderSnapshot;
  readonly onClose: () => void;
  readonly onCopy: () => void;
};

function SnapshotModal({ snapshot, onClose, onCopy }: SnapshotModalProps): ReactElement {
  const jsonText = JSON.stringify(snapshot.boulder_snapshot, null, 2);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="snapshot-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4"
      data-testid="instance-snapshot-modal"
    >
      <div className="flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <div>
            <h2 id="snapshot-modal-title" className="text-sm font-semibold text-slate-900">
              Boulder snapshot
            </h2>
            <p className="mt-0.5 font-mono text-xs text-slate-500">
              continuations={snapshot.continuation_count} captured_at={snapshot.captured_at}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onCopy}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50"
              data-testid="instance-snapshot-copy"
            >
              <Copy className="size-3.5" aria-hidden="true" />
              Copy
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close snapshot"
              className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
            >
              <span aria-hidden="true" className="text-lg leading-none">
                &times;
              </span>
            </button>
          </div>
        </header>
        <pre
          className="overflow-auto bg-slate-950 px-4 py-3 font-mono text-xs leading-5 text-slate-100"
          data-testid="instance-snapshot-json"
        >
          {jsonText}
        </pre>
      </div>
    </div>
  );
}

type ToastViewProps = {
  readonly toast: Toast;
};

function ToastView({ toast }: ToastViewProps): ReactElement {
  const isError = toast.kind === 'error';
  return (
    <div
      role="status"
      aria-live="polite"
      className={`mb-6 flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm ${
        isError
          ? 'border-red-200 bg-red-50 text-red-800'
          : 'border-emerald-200 bg-emerald-50 text-emerald-800'
      }`}
      data-testid="instance-toast"
    >
      {isError ? <AlertCircle className="size-4 shrink-0" aria-hidden="true" /> : null}
      <p>{toast.message}</p>
    </div>
  );
}
