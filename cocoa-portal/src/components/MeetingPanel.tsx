import {
  AlertCircle,
  CalendarDays,
  LoaderCircle,
  Play,
  Square,
  Users,
  XCircle,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiError, api } from '@/lib/api';
import {
  cancelMeeting,
  createMeeting,
  endMeeting,
  fetchMeetings,
  startMeeting,
} from '@/lib/api/meetings';
import type { Meeting, MeetingStatus, Membership } from '@/lib/types';

const MEETING_STATUS_BADGE: Readonly<Record<MeetingStatus, string>> = {
  scheduled: 'border-blue-200 bg-blue-50 text-blue-700',
  active: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  ended: 'border-slate-200 bg-slate-50 text-slate-600',
  cancelled: 'border-red-200 bg-red-50 text-red-600',
};

const ACTIONABLE_STATUSES: Readonly<Record<MeetingStatus, 'start' | 'end' | 'cancel' | null>> = {
  scheduled: 'start',
  active: 'end',
  ended: null,
  cancelled: null,
};

function toDatetimeLocalValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function membershipLabel(m: Membership): string {
  return (
    m.nickname?.trim() ||
    m.username?.trim() ||
    m.entity_name?.trim() ||
    m.entity_slug?.trim() ||
    m.id
  );
}

export default function MeetingPanel({ workspaceId }: { readonly workspaceId: string }) {
  const { t } = useTranslation();
  const [meetings, setMeetings] = useState<readonly Meeting[]>([]);
  const [memberships, setMemberships] = useState<readonly Membership[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [agenda, setAgenda] = useState('');
  const [scheduledAt, setScheduledAt] = useState(() =>
    toDatetimeLocalValue(new Date(Date.now() + 60 * 60 * 1000)),
  );
  const [participantIds, setParticipantIds] = useState<ReadonlySet<string>>(new Set());
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [meetingPage, membershipPage] = await Promise.all([
        fetchMeetings(workspaceId),
        api<{ readonly items: readonly Membership[]; readonly total: number }>(
          `/messaging/memberships?workspace_id=${encodeURIComponent(workspaceId)}`,
        ),
      ]);
      setMeetings(meetingPage.items);
      setTotal(meetingPage.total);
      setMemberships(membershipPage.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('errors.network'));
      setMeetings([]);
      setTotal(0);
      setMemberships([]);
    } finally {
      setLoading(false);
    }
  }, [t, workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const membershipById = useMemo(() => {
    const map = new Map<string, Membership>();
    for (const m of memberships) map.set(m.id, m);
    return map;
  }, [memberships]);

  const resolveError = useCallback(
    (error: unknown, fallbackKey: string): string => {
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
      return t(fallbackKey);
    },
    [t],
  );

  const applyMeeting = useCallback((next: Meeting) => {
    setMeetings((prev) => {
      const exists = prev.some((m) => m.id === next.id);
      if (exists) return prev.map((m) => (m.id === next.id ? next : m));
      return [next, ...prev];
    });
  }, []);

  const handleCreate = useCallback(async () => {
    const trimmedTitle = title.trim();
    if (trimmedTitle.length === 0) {
      setFormError(t('meetings.titleRequired'));
      return;
    }
    if (scheduledAt.length === 0) {
      setFormError(t('meetings.scheduledAtRequired'));
      return;
    }
    setCreating(true);
    setFormError(null);
    try {
      const meeting = await createMeeting({
        workspace_id: workspaceId,
        title: trimmedTitle,
        agenda: agenda.trim().length > 0 ? agenda.trim() : null,
        scheduled_at: new Date(scheduledAt).toISOString(),
        participant_membership_ids: [...participantIds],
      });
      applyMeeting(meeting);
      setCreateOpen(false);
      setTitle('');
      setAgenda('');
      setParticipantIds(new Set());
      setScheduledAt(toDatetimeLocalValue(new Date(Date.now() + 60 * 60 * 1000)));
    } catch (err) {
      setFormError(resolveError(err, 'meetings.failed'));
    } finally {
      setCreating(false);
    }
  }, [agenda, applyMeeting, participantIds, resolveError, scheduledAt, t, title, workspaceId]);

  const runAction = useCallback(
    async (meeting: Meeting, action: 'start' | 'end' | 'cancel') => {
      const confirmKey =
        action === 'start'
          ? t('meetings.startConfirm', { title: meeting.title })
          : action === 'end'
            ? t('meetings.endConfirm', { title: meeting.title })
            : t('meetings.cancelConfirm', { title: meeting.title });
      if (!window.confirm(confirmKey)) return;
      setBusyId(meeting.id);
      setError(null);
      try {
        const runner =
          action === 'start' ? startMeeting : action === 'end' ? endMeeting : cancelMeeting;
        const next = await runner(meeting.id);
        applyMeeting(next);
        await load();
      } catch (err) {
        setError(resolveError(err, 'meetings.failed'));
      } finally {
        setBusyId(null);
      }
    },
    [applyMeeting, load, resolveError, t],
  );

  const toggleParticipant = useCallback((membershipId: string) => {
    setParticipantIds((prev) => {
      const next = new Set(prev);
      if (next.has(membershipId)) {
        next.delete(membershipId);
      } else {
        next.add(membershipId);
      }
      return next;
    });
  }, []);

  return (
    <div className="h-full space-y-4 overflow-y-auto p-6">
      <article className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-slate-900">{t('meetings.title')}</h2>
          {!createOpen ? (
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-blue-500"
            >
              <CalendarDays className="size-3.5" aria-hidden="true" />
              {t('meetings.createTitle')}
            </button>
          ) : null}
        </div>

        {createOpen ? (
          <form
            className="mt-4 space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              void handleCreate();
            }}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
                {t('meetings.fieldTitle')}
                <input
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder={t('meetings.titlePlaceholder')}
                  disabled={creating}
                  className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              </label>
              <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
                {t('meetings.fieldScheduledAt')}
                <input
                  type="datetime-local"
                  value={scheduledAt}
                  onChange={(event) => setScheduledAt(event.target.value)}
                  disabled={creating}
                  className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                />
              </label>
            </div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
              {t('meetings.fieldAgenda')}
              <textarea
                value={agenda}
                onChange={(event) => setAgenda(event.target.value)}
                placeholder={t('meetings.agendaPlaceholder')}
                disabled={creating}
                rows={3}
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            <fieldset className="block text-xs font-semibold uppercase tracking-wide text-slate-600">
              <legend>
                {t('meetings.fieldParticipants')}
                <span className="ml-2 font-normal normal-case text-slate-500">
                  {t('meetings.participantsSelected', { count: participantIds.size })}
                </span>
              </legend>
              <div className="mt-1.5 max-h-40 space-y-1 overflow-y-auto rounded-lg border border-slate-200 px-3 py-2">
                {memberships.length === 0 ? (
                  <p className="py-1 text-xs font-normal normal-case text-slate-500">
                    {t('meetings.noParticipants')}
                  </p>
                ) : (
                  memberships.map((m) => (
                    <label
                      key={m.id}
                      className="flex items-center gap-2 py-0.5 text-xs font-normal normal-case text-slate-700"
                    >
                      <input
                        type="checkbox"
                        checked={participantIds.has(m.id)}
                        onChange={() => toggleParticipant(m.id)}
                        disabled={creating}
                        className="size-3.5 rounded border-slate-300 text-blue-600"
                      />
                      <span className="min-w-0 truncate">{membershipLabel(m)}</span>
                    </label>
                  ))
                )}
              </div>
            </fieldset>
            {formError !== null ? (
              <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">
                {formError}
              </p>
            ) : null}
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={creating}
                className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
              >
                {creating ? (
                  <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
                ) : null}
                {t('meetings.create')}
              </button>
              <button
                type="button"
                onClick={() => {
                  setCreateOpen(false);
                  setFormError(null);
                }}
                disabled={creating}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              >
                {t('common.cancel')}
              </button>
            </div>
          </form>
        ) : null}
      </article>

      {error !== null ? (
        <p
          role="alert"
          className="flex items-center gap-2 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700"
        >
          <AlertCircle className="size-3.5 shrink-0" aria-hidden="true" />
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="flex items-center gap-2 text-sm text-slate-500">
          <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
          {t('common.loading')}
        </p>
      ) : meetings.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-200 bg-white p-6 text-center">
          <CalendarDays className="mx-auto size-8 text-slate-400" aria-hidden="true" />
          <h3 className="mt-3 text-sm font-semibold text-slate-900">{t('meetings.empty')}</h3>
          <p className="mt-1 text-sm text-slate-500">{t('meetings.emptyDetail')}</p>
        </div>
      ) : (
        <article className="rounded-lg border border-slate-200 bg-white p-4">
          <ul className="space-y-3">
            {meetings.map((meeting) => {
              const primaryAction = ACTIONABLE_STATUSES[meeting.status];
              return (
                <li
                  key={meeting.id}
                  className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-3"
                >
                  <div className="flex flex-wrap items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate text-sm font-semibold text-slate-900">
                          {meeting.title}
                        </p>
                        <span
                          className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-xs font-medium ${MEETING_STATUS_BADGE[meeting.status]}`}
                        >
                          {t(`meetings.statuses.${meeting.status}`)}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">
                        {t('meetings.scheduledAtLabel')}:{' '}
                        {new Date(meeting.scheduled_at).toLocaleString()}
                        {meeting.ended_at !== null
                          ? ` · ${t('meetings.endedAtLabel')}: ${new Date(meeting.ended_at).toLocaleString()}`
                          : ''}
                      </p>
                      {meeting.agenda !== null && meeting.agenda.length > 0 ? (
                        <p className="mt-1 whitespace-pre-wrap text-xs text-slate-600">
                          {meeting.agenda}
                        </p>
                      ) : null}
                      <p className="mt-1 flex items-center gap-1 text-xs text-slate-500">
                        <Users className="size-3.5 shrink-0" aria-hidden="true" />
                        {(meeting.participants ?? []).length > 0
                          ? t('meetings.participantsCount', {
                              count: (meeting.participants ?? []).length,
                            })
                          : t('meetings.noParticipants')}
                        {(meeting.participants ?? []).length > 0 ? (
                          <span className="truncate">
                            :{' '}
                            {(meeting.participants ?? [])
                              .map((p) => {
                                const member = membershipById.get(p.membership_id);
                                return member !== undefined
                                  ? membershipLabel(member)
                                  : t('meetings.unknownParticipant');
                              })
                              .join(', ')}
                          </span>
                        ) : null}
                      </p>
                    </div>
                    <div className="flex shrink-0 gap-1.5">
                      {primaryAction !== null ? (
                        <button
                          type="button"
                          onClick={() => void runAction(meeting, primaryAction)}
                          disabled={busyId !== null}
                          className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold disabled:opacity-60 ${
                            primaryAction === 'start'
                              ? 'bg-emerald-600 text-white hover:bg-emerald-500'
                              : 'bg-blue-600 text-white hover:bg-blue-500'
                          }`}
                        >
                          {busyId === meeting.id ? (
                            <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
                          ) : primaryAction === 'start' ? (
                            <Play className="size-3.5" aria-hidden="true" />
                          ) : (
                            <Square className="size-3.5" aria-hidden="true" />
                          )}
                          {t(primaryAction === 'start' ? 'meetings.start' : 'meetings.end')}
                        </button>
                      ) : null}
                      {meeting.status === 'scheduled' || meeting.status === 'active' ? (
                        <button
                          type="button"
                          onClick={() => void runAction(meeting, 'cancel')}
                          disabled={busyId !== null}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
                        >
                          <XCircle className="size-3.5" aria-hidden="true" />
                          {t('meetings.cancel')}
                        </button>
                      ) : null}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-xs text-slate-400">{t('meetings.count', { total })}</p>
        </article>
      )}
    </div>
  );
}
