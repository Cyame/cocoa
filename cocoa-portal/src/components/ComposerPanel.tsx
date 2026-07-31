import { AlertCircle, LoaderCircle, MessageSquare, Send } from 'lucide-react';
import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CommandAutocomplete } from '@/components/CommandAutocomplete';
import { MentionAutocomplete } from '@/components/MentionAutocomplete';
import { ApiError, api } from '@/lib/api';
import { streamComposerTurn } from '@/lib/composerStream';
import {
  type Compartment,
  parse_turn,
  SlashParserError,
  segmentCompartments,
  type Turn,
} from '@/lib/slash-parser';
import { useComposerDraftStore } from '@/stores/composerDraftStore';
import { useSessionStore } from '@/stores/session';

type DeliveryItem = {
  readonly delivered: boolean;
  readonly reason: string | null;
  readonly instance_id: string | null;
  readonly turn_id: string | null;
};

type DirectiveResultRow = {
  readonly target_entity: string | null;
  readonly cmd: string | null;
  readonly delivery: readonly DeliveryItem[];
};

type MessageSendResult = {
  readonly directives: readonly string[];
  readonly general_text: string | null;
  readonly results: readonly DirectiveResultRow[];
};

type StreamLane = {
  readonly turnId: string;
  readonly target: string;
  status: 'responding' | 'completed' | 'failed';
  text: string;
  error?: string;
};

type ComposerPanelProps = {
  readonly workspaceId: string;
  readonly compact?: boolean;
};

export default function ComposerPanel({ workspaceId, compact = false }: ComposerPanelProps) {
  const { t } = useTranslation();
  const token = useSessionStore((s) => s.token);
  const draft = useComposerDraftStore((s) => s.draft);
  const consumeDraft = useComposerDraftStore((s) => s.consumeDraft);

  const [text, setText] = useState('');
  const [parseError, setParseError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [deliveryRows, setDeliveryRows] = useState<readonly DirectiveResultRow[]>([]);
  const [lanes, setLanes] = useState<StreamLane[]>([]);
  const [cmdMenuOpen, setCmdMenuOpen] = useState(false);
  const [presetByEntitySlug, setPresetByEntitySlug] = useState<
    Readonly<Record<string, string | null>>
  >({});
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (draft === null) return;
    const next = consumeDraft();
    if (next !== null) {
      setText(next);
      requestAnimationFrame(() => {
        const el = textareaRef.current;
        if (el !== null) {
          el.focus();
          el.setSelectionRange(next.length, next.length);
        }
      });
    }
  }, [draft, consumeDraft]);

  useEffect(() => {
    let cancelled = false;
    void api<{ items: { slug: string; preset_slug: string | null }[] }>(
      `/workspaces/${encodeURIComponent(workspaceId)}/mention-candidates`,
    )
      .then((res) => {
        if (cancelled) return;
        const map: Record<string, string | null> = {};
        for (const item of res.items) {
          map[item.slug] = item.preset_slug;
        }
        setPresetByEntitySlug(map);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const { turn, error } = useMemo<{ turn: Turn | null; error: string | null }>(() => {
    try {
      return { turn: parse_turn(text), error: null };
    } catch (e) {
      const msg = e instanceof SlashParserError ? e.message : t('composer.parseError');
      return { turn: null, error: msg };
    }
  }, [text, t]);

  useEffect(() => {
    setParseError(error);
  }, [error]);

  const compartments = useMemo<readonly Compartment[]>(() => {
    if (turn === null) return [];
    return segmentCompartments(turn);
  }, [turn]);

  const targetSlugs = useMemo<readonly string[]>(() => {
    if (turn === null) return [];
    const seen = new Set<string>();
    const result: string[] = [];
    for (const d of turn.directives) {
      if (d.target_entity !== null && !seen.has(d.target_entity)) {
        seen.add(d.target_entity);
        result.push(d.target_entity);
      }
    }
    return result;
  }, [turn]);

  const bareEmployeeCmdHint = useMemo(() => {
    if (turn === null) return false;
    for (const d of turn.directives) {
      if (d.target_entity === null && d.cmd && !['/read', '/list', '/write', '/archive'].includes(d.cmd)) {
        if (
          ['/interrupt', '/pause', '/resume', '/status', '/snapshot', '/distill', '/consolidate', '/reflect'].includes(
            d.cmd,
          )
        ) {
          return true;
        }
        // per-preset style bare command
        if (!GLOBAL_LIKE.has(d.cmd)) return true;
      }
    }
    return false;
  }, [turn]);

  const canSend = text.trim().length > 0 && parseError === null && !sending;

  async function handleSend() {
    if (!canSend) return;
    setSending(true);
    setSendError(null);
    setDeliveryRows([]);
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setLanes([]);
    try {
      const result = await api<MessageSendResult>('/messaging/messages', {
        method: 'POST',
        body: JSON.stringify({ turn_text: text, workspace_id: workspaceId }),
      });
      setDeliveryRows(result.results);

      const turnIds: { turnId: string; target: string }[] = [];
      for (const row of result.results) {
        for (const d of row.delivery) {
          if (d.delivered && d.turn_id) {
            turnIds.push({
              turnId: d.turn_id,
              target: row.target_entity ?? d.instance_id ?? 'unknown',
            });
          }
        }
      }

      if (turnIds.length > 0) {
        setLanes(
          turnIds.map((t) => ({
            turnId: t.turnId,
            target: t.target,
            status: 'responding',
            text: '',
          })),
        );
        await Promise.all(
          turnIds.map(async ({ turnId }) => {
            try {
              await streamComposerTurn(
                workspaceId,
                turnId,
                token,
                (frame) => {
                  setLanes((prev) =>
                    prev.map((lane) => {
                      if (lane.turnId !== turnId) return lane;
                      if (frame.type === 'chat.response.chunk' && frame.token) {
                        return {
                          ...lane,
                          status: 'responding',
                          text: lane.text + frame.token,
                        };
                      }
                      if (frame.type === 'chat.response.done') {
                        return { ...lane, status: 'completed' };
                      }
                      if (frame.type === 'chat.response.error') {
                        return {
                          ...lane,
                          status: 'failed',
                          error: frame.message ?? t('composer.instanceOffline'),
                        };
                      }
                      return lane;
                    }),
                  );
                },
                ac.signal,
              );
            } catch (e) {
              if (ac.signal.aborted) return;
              setLanes((prev) =>
                prev.map((lane) =>
                  lane.turnId === turnId
                    ? {
                        ...lane,
                        status: 'failed',
                        error: e instanceof Error ? e.message : t('composer.streamFailed'),
                      }
                    : lane,
                ),
              );
            }
          }),
        );
      }
    } catch (e) {
      setSendError(e instanceof ApiError ? e.message : t('composer.sendFailed'));
    } finally {
      setSending(false);
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      void handleSend();
    }
  }

  const textareaHeight = compact ? 'h-40' : 'h-64';

  return (
    <section
      className={`flex h-full flex-col ${compact ? 'p-3' : 'p-6'}`}
      aria-label={t('composer.title')}
    >
      {!compact ? (
        <header className="mb-4 flex items-center gap-2">
          <MessageSquare className="size-5 text-slate-700" aria-hidden="true" />
          <h2 className="text-lg font-semibold text-slate-900">{t('composer.title')}</h2>
        </header>
      ) : null}

      {parseError !== null ? (
        <div
          role="alert"
          className="mb-3 flex items-center gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-800"
        >
          <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
          <span>{parseError}</span>
        </div>
      ) : null}

      {sendError !== null ? (
        <div
          role="alert"
          className="mb-3 flex items-center gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-800"
        >
          <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
          <span>{sendError}</span>
        </div>
      ) : null}

      {bareEmployeeCmdHint ? (
        <div className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          {t('composer.needAtTarget')}
        </div>
      ) : null}

      {lanes.length > 0 ? (
        <ul className="mb-2 max-h-40 space-y-2 overflow-y-auto">
          {lanes.map((lane) => (
            <li
              key={lane.turnId}
              className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1.5 text-xs"
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <code className="font-mono text-slate-800">@{lane.target}</code>
                <StatusBadge status={lane.status} />
              </div>
              <pre className="whitespace-pre-wrap break-words font-sans text-slate-700">
                {lane.text || (lane.status === 'responding' ? '…' : '')}
              </pre>
              {lane.error ? <p className="mt-1 text-red-700">{lane.error}</p> : null}
            </li>
          ))}
        </ul>
      ) : null}

      {deliveryRows.length > 0 && lanes.length === 0 ? (
        <ul className="mb-2 max-h-24 overflow-y-auto text-xs text-slate-700">
          {deliveryRows.flatMap((row) =>
            row.delivery.map((d, i) => (
              <li key={`${row.target_entity}-${i}`} className="font-mono">
                @{row.target_entity ?? '?'}:{' '}
                {d.delivered ? t('composer.delivered') : d.reason ?? t('composer.blocked')}
              </li>
            )),
          )}
        </ul>
      ) : null}

      <div className="relative min-h-0 flex-1">
        <textarea
          ref={textareaRef}
          id="composer-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={t('composer.placeholder')}
          className={`${textareaHeight} w-full rounded-lg border border-slate-300 p-3 font-mono text-sm text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500`}
          spellCheck={false}
        />
        <CommandAutocomplete
          textareaRef={textareaRef}
          text={text}
          onTextChange={setText}
          targetSlugs={targetSlugs}
          presetByEntitySlug={presetByEntitySlug}
          onOpenChange={setCmdMenuOpen}
        />
        <MentionAutocomplete
          textareaRef={textareaRef}
          text={text}
          onTextChange={setText}
          workspaceId={workspaceId}
          suppressed={cmdMenuOpen}
        />
      </div>

      {compartments.length > 0 ? (
        <ul className="mt-2 max-h-20 overflow-y-auto text-xs text-slate-600">
          {compartments.map((c) => (
            <li key={c.label} className="truncate font-mono">
              {c.label === 'general'
                ? t('composer.compartmentGeneral')
                : `@${c.label}`}
              :{' '}
              {c.directives.length > 0
                ? c.directives
                    .map((d) => d.cmd || d.args.join(' ') || '(chat)')
                    .join(', ')
                : c.general_text ?? '—'}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="mt-3 flex items-center justify-between gap-2">
        <span className="text-[10px] text-slate-400">{t('composer.sendHint')}</span>
        <button
          type="button"
          onClick={() => void handleSend()}
          disabled={!canSend}
          className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {sending ? (
            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
          ) : (
            <Send className="size-4" aria-hidden="true" />
          )}
          {sending ? t('composer.sending') : t('composer.send')}
        </button>
      </div>
    </section>
  );
}

const GLOBAL_LIKE = new Set(['/read', '/list', '/write', '/archive']);

function StatusBadge({ status }: { readonly status: StreamLane['status'] }) {
  const { t } = useTranslation();
  const label =
    status === 'responding'
      ? t('composer.statusResponding')
      : status === 'completed'
        ? t('composer.statusDone')
        : t('composer.statusFailed');
  const cls =
    status === 'responding'
      ? 'bg-amber-100 text-amber-800'
      : status === 'completed'
        ? 'bg-emerald-100 text-emerald-800'
        : 'bg-red-100 text-red-800';
  return <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${cls}`}>{label}</span>;
}
