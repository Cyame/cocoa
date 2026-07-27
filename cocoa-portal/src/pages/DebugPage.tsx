import { Bug, Download, Filter, LoaderCircle, RefreshCw } from 'lucide-react';
import { Fragment, useCallback, useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import type { Event, JsonObject } from '@/lib/types';

const POLL_INTERVAL_MS = 5000;
const DEFAULT_LIMIT = 100;

const RESOURCE_TYPES = [
  'instance',
  'office',
  'membership',
  'corridor',
  'message',
  'memory_entry',
  'learning',
  'blackboard',
] as const;

type FilterState = {
  readonly typePrefix: string;
  readonly resourceType: string;
  readonly resourceId: string;
  readonly requestId: string;
  readonly since: string;
  readonly until: string;
};

const INITIAL_FILTERS: FilterState = {
  typePrefix: 'harness.',
  resourceType: '',
  resourceId: '',
  requestId: '',
  since: '',
  until: '',
};

type EventPage = {
  readonly items: readonly Event[];
  readonly next_cursor: string | null;
  readonly total: number | null;
};

function toIso(localValue: string): string | null {
  if (localValue.length === 0) return null;
  const date = new Date(localValue);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString();
}

function buildEventsPath(filters: FilterState): string {
  const params = new URLSearchParams();
  params.set('limit', String(DEFAULT_LIMIT));
  if (filters.typePrefix.length > 0) params.set('type_prefix', filters.typePrefix);
  if (filters.resourceType.length > 0) params.set('resource_type', filters.resourceType);
  if (filters.resourceId.length > 0) params.set('resource_id', filters.resourceId);
  if (filters.requestId.length > 0) params.set('request_id', filters.requestId);
  const sinceIso = toIso(filters.since);
  if (sinceIso !== null) params.set('since', sinceIso);
  const untilIso = toIso(filters.until);
  if (untilIso !== null) params.set('until', untilIso);
  return `/events?${params.toString()}`;
}

function formatResource(event: Event): string {
  if (event.resource_type === null && event.resource_id === null) return '-';
  if (event.resource_type === null) return event.resource_id ?? '-';
  if (event.resource_id === null) return event.resource_type;
  return `${event.resource_type}:${event.resource_id}`;
}

function previewPayload(payload: JsonObject): string {
  const text = JSON.stringify(payload);
  return text.length > 80 ? `${text.slice(0, 77)}...` : text;
}

export default function DebugPage() {
  const [draftFilters, setDraftFilters] = useState<FilterState>(INITIAL_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<FilterState>(INITIAL_FILTERS);
  const [events, setEvents] = useState<readonly Event[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const loadEvents = useCallback(async (filters: FilterState) => {
    try {
      const path = buildEventsPath(filters);
      const page = await api<EventPage>(path);
      setEvents(page.items);
      setLastUpdated(new Date().toISOString());
      setErrorMessage(null);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 401) return;
        setErrorMessage(error.message);
      } else {
        throw error;
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    const safeLoad = async () => {
      if (!active) return;
      await loadEvents(appliedFilters);
    };
    setIsLoading(true);
    void safeLoad();
    const intervalId = window.setInterval(() => {
      void safeLoad();
    }, POLL_INTERVAL_MS);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [appliedFilters, loadEvents]);

  const handleApply = () => {
    setIsLoading(true);
    setAppliedFilters(draftFilters);
  };

  const handleRefresh = () => {
    setIsLoading(true);
    void loadEvents(appliedFilters);
  };

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(events, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `cocoa-events-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  };

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const updateFilter = (key: keyof FilterState, value: string) => {
    setDraftFilters((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <section className="w-full p-6 lg:p-8" aria-labelledby="debug-page-title">
      <header className="mb-6 flex items-start gap-4">
        <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-slate-900 text-white shadow-sm">
          <Bug className="size-6" aria-hidden="true" />
        </span>
        <div className="flex-1">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-600">
            Audit stream
          </p>
          <h1 id="debug-page-title" className="mt-1 text-3xl font-semibold tracking-tight text-slate-950">
            Debug
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            Raw audit event stream with cursor pagination. Auto-refreshes every 5 seconds;
            events may be delayed up to 5s.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={handleRefresh}
            className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <RefreshCw className="size-4" aria-hidden="true" />
            Refresh
          </button>
          <button
            type="button"
            onClick={handleExport}
            className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <Download className="size-4" aria-hidden="true" />
            Export
          </button>
        </div>
      </header>

      <div className="mb-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-700">
            <span>Type prefix</span>
            <input
              type="text"
              value={draftFilters.typePrefix}
              onChange={(e) => updateFilter('typePrefix', e.target.value)}
              placeholder="harness."
              aria-label="Filter by type prefix"
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-700">
            <span>Resource type</span>
            <select
              value={draftFilters.resourceType}
              onChange={(e) => updateFilter('resourceType', e.target.value)}
              aria-label="Filter by resource type"
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="">(all)</option>
              {RESOURCE_TYPES.map((rt) => (
                <option key={rt} value={rt}>
                  {rt}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-700">
            <span>Resource ID</span>
            <input
              type="text"
              value={draftFilters.resourceId}
              onChange={(e) => updateFilter('resourceId', e.target.value)}
              placeholder="uuid"
              aria-label="Filter by resource id"
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-700">
            <span>Request ID</span>
            <input
              type="text"
              value={draftFilters.requestId}
              onChange={(e) => updateFilter('requestId', e.target.value)}
              placeholder="uuid"
              aria-label="Filter by request id"
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-700">
            <span>Since</span>
            <input
              type="datetime-local"
              value={draftFilters.since}
              onChange={(e) => updateFilter('since', e.target.value)}
              aria-label="Filter events since this timestamp"
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-700">
            <span>Until</span>
            <input
              type="datetime-local"
              value={draftFilters.until}
              onChange={(e) => updateFilter('until', e.target.value)}
              aria-label="Filter events until this timestamp"
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </label>
        </div>
        <div className="mt-3 flex items-center justify-between">
          <button
            type="button"
            onClick={handleApply}
            className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <Filter className="size-4" aria-hidden="true" />
            Apply
          </button>
          <p className="text-xs text-slate-500">
            {lastUpdated !== null ? `Last updated ${new Date(lastUpdated).toLocaleTimeString()}` : null}
          </p>
        </div>
      </div>

      {errorMessage !== null ? (
        <div
          role="alert"
          className="mb-4 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          <Bug className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-semibold">Failed to load events</p>
            <p className="mt-1 text-red-700">{errorMessage}</p>
          </div>
        </div>
      ) : null}

      <div className="overflow-auto rounded-xl border border-slate-200 bg-white shadow-sm" style={{ maxHeight: '70vh' }}>
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-600">
            <tr>
              <th scope="col" className="border-b border-slate-200 px-4 py-3 font-semibold">Created at</th>
              <th scope="col" className="border-b border-slate-200 px-4 py-3 font-semibold">Type</th>
              <th scope="col" className="border-b border-slate-200 px-4 py-3 font-semibold">Actor</th>
              <th scope="col" className="border-b border-slate-200 px-4 py-3 font-semibold">Resource</th>
              <th scope="col" className="border-b border-slate-200 px-4 py-3 font-semibold">Payload</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && events.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-12 text-center text-slate-500">
                  <span className="inline-flex items-center gap-2">
                    <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                    Loading events
                  </span>
                </td>
              </tr>
            ) : null}

            {!isLoading && errorMessage === null && events.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-12 text-center text-slate-500">
                  No events match the current filters.
                </td>
              </tr>
            ) : null}

            {events.map((event) => {
              const isExpanded = expandedIds.has(event.id);
              return (
                <Fragment key={event.id}>
                  <tr
                    onClick={() => toggleExpand(event.id)}
                    className="cursor-pointer border-b border-slate-100 transition-colors hover:bg-slate-50"
                  >
                    <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs text-slate-600">
                      {event.created_at}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-slate-900">{event.type}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-700">
                      <span className="font-medium">{event.actor_type}</span>
                      {event.actor_id !== null ? (
                        <span className="ml-1 text-slate-500">{event.actor_id}</span>
                      ) : null}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-slate-700">
                      {formatResource(event)}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-slate-500">
                      {previewPayload(event.payload)}
                    </td>
                  </tr>
                  {isExpanded ? (
                    <tr className="border-b border-slate-100 bg-slate-50">
                      <td colSpan={5} className="px-4 py-3">
                        <pre className="overflow-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">
                          {JSON.stringify(event.payload, null, 2)}
                        </pre>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-slate-500">
        Showing {events.length} event{events.length === 1 ? '' : 's'} · polling every 5s
      </p>
    </section>
  );
}
