import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  LoaderCircle,
  Plus,
  Syringe,
  Trash,
  UserRound,
} from 'lucide-react';
import { Fragment, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError, api } from '@/lib/api';
import { injectInstance } from '@/lib/api/instances';
import {
  buildInjectPayload,
  buildInstanceEventsPath,
  type HarnessEventPage,
  mergeHarnessEvents,
} from '@/lib/instanceHarness';
import type { Entity, Event, InjectDeliveryMode, InjectKind, Instance } from '@/lib/types';

const EVENTS_POLL_INTERVAL_MS = 5000;

const INJECT_KINDS: readonly InjectKind[] = [
  'collab_inject',
  'gene_inject',
  'capability_inject',
  'cerebellum_route',
];

const DELIVERY_MODES: readonly InjectDeliveryMode[] = ['notify', 'soft_inject', 'wake'];

const EVENT_DOT_CLASS: Readonly<Record<string, string>> = {
  'harness.inject_requested': 'bg-amber-500',
  'harness.inject_applied': 'bg-emerald-500',
  'harness.inject_failed': 'bg-red-500',
};

function eventDotClass(eventType: string): string {
  const known = EVENT_DOT_CLASS[eventType];
  if (known !== undefined) return known;
  return eventType.startsWith('harness.report_') ? 'bg-blue-500' : 'bg-slate-400';
}

function summarizePayload(event: Event): string {
  const tldr = event.payload.tldr;
  if (typeof tldr === 'string' && tldr.length > 0) return tldr;
  const text = JSON.stringify(event.payload);
  return text.length > 80 ? `${text.slice(0, 77)}...` : text;
}

type InstancesPanelProps = {
  readonly instances: readonly Instance[];
  readonly entities: readonly Entity[];
  readonly emptyTitle: string;
  readonly emptyDetail: string;
  readonly actionLabel: string;
  readonly onAction: () => void;
  readonly removeLabel: string;
  readonly onRemove: (instanceId: string, title: string) => void;
};

export default function InstancesPanel({
  instances,
  entities,
  emptyTitle,
  emptyDetail,
  actionLabel,
  onAction,
  removeLabel,
  onRemove,
}: InstancesPanelProps) {
  const { t } = useTranslation();
  const [expandedIds, setExpandedIds] = useState<ReadonlySet<string>>(new Set());

  const toggleExpanded = useCallback((instanceId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(instanceId)) {
        next.delete(instanceId);
      } else {
        next.add(instanceId);
      }
      return next;
    });
  }, []);

  if (instances.length === 0) {
    return (
      <div className="grid h-full place-items-center p-6 text-center">
        <div>
          <UserRound className="mx-auto size-8 text-slate-400" aria-hidden="true" />
          <h2 className="mt-4 text-sm font-semibold text-slate-900">{emptyTitle}</h2>
          <p className="mt-2 text-sm text-slate-500">{emptyDetail}</p>
          <button
            type="button"
            onClick={onAction}
            data-testid="workspace-introduce-cta"
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500"
          >
            <Plus className="size-4" aria-hidden="true" />
            {actionLabel}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 justify-end border-b border-slate-200 bg-white px-4 py-2">
        <button
          type="button"
          onClick={onAction}
          data-testid="workspace-introduce-cta"
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500"
        >
          <Plus className="size-3.5" aria-hidden="true" />
          {actionLabel}
        </button>
      </div>
      <ul className="space-y-3 overflow-y-auto p-6">
        {instances.map((inst) => {
          const entity = entities.find((e) => e.id === inst.entity_id);
          const title = entity?.display_name ?? entity?.name ?? inst.entity_id;
          const isExpanded = expandedIds.has(inst.id);
          return (
            <Fragment key={inst.id}>
              <li className="rounded-lg border border-slate-200 bg-white">
                <div className="flex items-center gap-3 p-4">
                  <button
                    type="button"
                    onClick={() => toggleExpanded(inst.id)}
                    aria-expanded={isExpanded}
                    aria-label={
                      isExpanded ? t('instanceDetail.collapse') : t('instanceDetail.expand')
                    }
                    data-testid={`workspace-expand-${inst.id}`}
                    className="inline-flex shrink-0 items-center rounded-md p-1 text-slate-500 hover:bg-slate-100"
                  >
                    {isExpanded ? (
                      <ChevronDown className="size-4" aria-hidden="true" />
                    ) : (
                      <ChevronRight className="size-4" aria-hidden="true" />
                    )}
                  </button>
                  <span className="grid size-9 shrink-0 place-items-center rounded-full bg-slate-100 text-slate-600">
                    <UserRound className="size-4" aria-hidden="true" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-slate-900">{title}</p>
                    <p className="mt-1 text-xs capitalize text-slate-500">{inst.status}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => onRemove(inst.id, title)}
                    data-testid={`workspace-remove-${inst.id}`}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50"
                  >
                    <Trash className="size-3.5" aria-hidden="true" />
                    {removeLabel}
                  </button>
                </div>
                {isExpanded ? (
                  <InstanceDetailSection instanceId={inst.id} instanceTitle={title} />
                ) : null}
              </li>
            </Fragment>
          );
        })}
      </ul>
    </div>
  );
}

function InstanceDetailSection({
  instanceId,
  instanceTitle,
}: {
  readonly instanceId: string;
  readonly instanceTitle: string;
}) {
  const { t } = useTranslation();
  const [events, setEvents] = useState<readonly Event[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [injectOpen, setInjectOpen] = useState(false);

  const fetchEvents = useCallback(async () => {
    const [injectPage, reportPage] = await Promise.all([
      api<HarnessEventPage>(buildInstanceEventsPath(instanceId, 'harness.inject_')),
      api<HarnessEventPage>(buildInstanceEventsPath(instanceId, 'harness.report_')),
    ]);
    return mergeHarnessEvents(injectPage.items, reportPage.items);
  }, [instanceId]);

  useEffect(() => {
    let active = true;
    const loadEvents = async () => {
      try {
        const merged = await fetchEvents();
        if (!active) return;
        setEvents(merged);
        setErrorMessage(null);
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError) {
          if (error.status === 401) return;
          setErrorMessage(error.message);
        } else {
          setErrorMessage(t('errors.network'));
        }
      } finally {
        if (active) setIsLoading(false);
      }
    };
    setIsLoading(true);
    void loadEvents();
    const intervalId = window.setInterval(() => {
      void loadEvents();
    }, EVENTS_POLL_INTERVAL_MS);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [fetchEvents, t]);

  const reloadEvents = useCallback(() => {
    fetchEvents()
      .then((merged) => {
        setEvents(merged);
        setErrorMessage(null);
      })
      .catch(() => {
        // best-effort; the next poll retries
      });
  }, [fetchEvents]);

  return (
    <div className="border-t border-slate-100 bg-slate-50 px-4 py-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          {t('instanceDetail.events.title')}
        </h3>
        <button
          type="button"
          onClick={() => setInjectOpen((open) => !open)}
          data-testid={`workspace-inject-${instanceId}`}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-blue-200 bg-white px-2.5 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-50"
        >
          <Syringe className="size-3.5" aria-hidden="true" />
          {t('instanceDetail.inject.action')}
        </button>
      </div>

      {injectOpen ? (
        <InjectForm
          instanceId={instanceId}
          instanceTitle={instanceTitle}
          onClose={() => setInjectOpen(false)}
          onSubmitted={reloadEvents}
        />
      ) : null}

      {isLoading && events.length === 0 ? (
        <p className="mt-3 flex items-center gap-2 text-xs text-slate-500">
          <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
          {t('common.loading')}
        </p>
      ) : null}

      {!isLoading && errorMessage !== null ? (
        <p
          role="alert"
          className="mt-3 flex items-center gap-2 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700"
        >
          <AlertCircle className="size-3.5 shrink-0" aria-hidden="true" />
          {errorMessage}
        </p>
      ) : null}

      {!isLoading && errorMessage === null && events.length === 0 ? (
        <p className="mt-3 text-xs text-slate-500">{t('instanceDetail.events.empty')}</p>
      ) : null}

      {events.length > 0 ? (
        <ul className="mt-3 max-h-64 space-y-1.5 overflow-y-auto">
          {events.map((event) => (
            <li
              key={event.id}
              className="flex items-start gap-2 rounded-md border border-slate-100 bg-white px-2.5 py-1.5"
            >
              <span
                aria-hidden="true"
                className={`mt-1.5 size-2 shrink-0 rounded-full ${eventDotClass(event.type)}`}
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="font-mono text-xs font-medium text-slate-900">
                    {event.type.replace(/^harness\./, '')}
                  </span>
                  <span className="font-mono text-xs text-slate-400">
                    {new Date(event.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="mt-0.5 truncate font-mono text-xs text-slate-500">
                  {summarizePayload(event)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

type InjectFormProps = {
  readonly instanceId: string;
  readonly instanceTitle: string;
  readonly onClose: () => void;
  readonly onSubmitted: () => void;
};

function InjectForm({ instanceId, instanceTitle, onClose, onSubmitted }: InjectFormProps) {
  const { t } = useTranslation();
  const [kind, setKind] = useState<InjectKind>('collab_inject');
  const [deliveryMode, setDeliveryMode] = useState<InjectDeliveryMode>('notify');
  const [tldr, setTldr] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{ tone: 'success' | 'error'; text: string } | null>(
    null,
  );

  const resolveError = useCallback(
    (error: unknown): string => {
      if (error instanceof ApiError) {
        const payload = error.payload;
        if (
          typeof payload === 'object' &&
          payload !== null &&
          'message_key' in payload &&
          typeof (payload as { message_key: unknown }).message_key === 'string'
        ) {
          const key = (payload as { message_key: string }).message_key;
          const translated = t(key, { defaultValue: '' });
          if (translated.length > 0) return translated;
        }
        return error.message;
      }
      return t('instanceDetail.inject.failed');
    },
    [t],
  );

  async function handleSubmit() {
    setSubmitting(true);
    setFeedback(null);
    try {
      await injectInstance(instanceId, buildInjectPayload({ kind, deliveryMode, tldr }));
      setFeedback({ tone: 'success', text: t('instanceDetail.inject.success') });
      setTldr('');
      onSubmitted();
    } catch (error) {
      setFeedback({ tone: 'error', text: resolveError(error) });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      className="mt-3 space-y-3 rounded-lg border border-slate-200 bg-white p-3"
      aria-label={t('instanceDetail.inject.title', { name: instanceTitle })}
      onSubmit={(event) => {
        event.preventDefault();
        void handleSubmit();
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
          {t('instanceDetail.inject.kind')}
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as InjectKind)}
            disabled={submitting}
            className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            {INJECT_KINDS.map((value) => (
              <option key={value} value={value}>
                {t(`instanceDetail.inject.kinds.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
          {t('instanceDetail.inject.deliveryMode')}
          <select
            value={deliveryMode}
            onChange={(event) => setDeliveryMode(event.target.value as InjectDeliveryMode)}
            disabled={submitting}
            className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            {DELIVERY_MODES.map((value) => (
              <option key={value} value={value}>
                {t(`instanceDetail.inject.deliveryModes.${value}`)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
        {t('instanceDetail.inject.tldr')}
        <input
          value={tldr}
          onChange={(event) => setTldr(event.target.value)}
          placeholder={t('instanceDetail.inject.tldrPlaceholder')}
          disabled={submitting}
          maxLength={400}
          className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
      </label>
      {feedback !== null ? (
        <p
          role={feedback.tone === 'error' ? 'alert' : 'status'}
          className={`rounded-md px-3 py-2 text-xs ${
            feedback.tone === 'error' ? 'bg-red-50 text-red-700' : 'bg-emerald-50 text-emerald-700'
          }`}
        >
          {feedback.text}
        </p>
      ) : null}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={submitting}
          className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
        >
          {submitting ? (
            <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
          ) : null}
          {t('instanceDetail.inject.submit')}
        </button>
        <button
          type="button"
          onClick={onClose}
          disabled={submitting}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
        >
          {t('common.cancel')}
        </button>
      </div>
    </form>
  );
}
