import { AlertCircle, LoaderCircle, MessageSquare, Send, Settings } from 'lucide-react';
import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CommandAutocomplete } from '@/components/CommandAutocomplete';
import { MentionAutocomplete } from '@/components/MentionAutocomplete';
import { ApiError, api } from '@/lib/api';
import {
  AgentThinkingStreamFilter,
  extractThinkingBlocks,
  stripAgentThinkingBlocks,
} from '@/lib/agentOutput';
import { streamComposerTurn } from '@/lib/composerStream';
import { renderMarkdown } from '@/lib/markdown';
import {
  type Compartment,
  parse_turn,
  SlashParserError,
  segmentCompartments,
  type Turn,
} from '@/lib/slash-parser';
import { useComposerDraftStore } from '@/stores/composerDraftStore';
import { useComposerSettingsStore } from '@/stores/composerSettingsStore';
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
  thinking: string;
  error?: string;
};

type TranscriptMessage = {
  readonly id: string;
  readonly role: string;
  readonly content: string;
  readonly target_entity: string | null;
  readonly turn_id: string | null;
  readonly status: string;
  readonly author_user_id?: string | null;
  readonly author_username?: string | null;
  readonly created_at: string | null;
};

type ComposerPanelProps = {
  readonly workspaceId: string;
  readonly compact?: boolean;
};

/** Prefer non-empty local content when server reload races ahead of finalize. */
function reconcileTranscript(
  server: readonly TranscriptMessage[],
  local: readonly TranscriptMessage[],
): TranscriptMessage[] {
  const localByTurn = new Map<string, TranscriptMessage>();
  for (const msg of local) {
    if (msg.role === 'assistant' && msg.turn_id && msg.content.trim()) {
      localByTurn.set(msg.turn_id, msg);
    }
  }
  const seen = new Set<string>();
  const out: TranscriptMessage[] = server.map((msg) => {
    seen.add(msg.id);
    if (msg.role !== 'assistant' || !msg.turn_id) return msg;
    const localMsg = localByTurn.get(msg.turn_id);
    if (!localMsg) return msg;
    if (msg.content.trim().length >= localMsg.content.trim().length) return msg;
    return { ...msg, content: localMsg.content, status: msg.status || localMsg.status };
  });
  for (const msg of local) {
    if (seen.has(msg.id)) continue;
    if (msg.role === 'assistant' && msg.turn_id) {
      const onServer = server.some((s) => s.role === 'assistant' && s.turn_id === msg.turn_id);
      if (onServer) continue;
    }
    out.push(msg);
  }
  return out;
}

function upsertAssistantBubble(
  prev: readonly TranscriptMessage[],
  lane: StreamLane,
): TranscriptMessage[] {
  const content = lane.error?.trim() ? lane.error : lane.text;
  const status =
    lane.status === 'responding' ? 'responding' : lane.status === 'failed' ? 'failed' : 'completed';
  const idx = prev.findIndex((m) => m.role === 'assistant' && m.turn_id === lane.turnId);
  if (idx >= 0) {
    const existing = prev[idx];
    const nextContent =
      content.trim().length >= (existing.content?.trim().length ?? 0) ? content : existing.content;
    const copy = [...prev];
    copy[idx] = {
      ...existing,
      content: nextContent,
      status,
      target_entity: lane.target || existing.target_entity,
    };
    return copy;
  }
  return [
    ...prev,
    {
      id: `local-assistant-${lane.turnId}`,
      role: 'assistant',
      content,
      target_entity: lane.target,
      turn_id: lane.turnId,
      status,
      author_user_id: null,
      author_username: null,
      created_at: new Date().toISOString(),
    },
  ];
}

export default function ComposerPanel({ workspaceId, compact = false }: ComposerPanelProps) {
  const { t } = useTranslation();
  const token = useSessionStore((s) => s.token);
  const draft = useComposerDraftStore((s) => s.draft);
  const consumeDraft = useComposerDraftStore((s) => s.consumeDraft);
  const showThinkingChain = useComposerSettingsStore((s) => s.showThinkingChain);
  const renderMd = useComposerSettingsStore((s) => s.renderMarkdown);
  const setShowThinkingChain = useComposerSettingsStore((s) => s.setShowThinkingChain);
  const setRenderMarkdown = useComposerSettingsStore((s) => s.setRenderMarkdown);

  const [text, setText] = useState('');
  const [parseError, setParseError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [deliveryRows, setDeliveryRows] = useState<readonly DirectiveResultRow[]>([]);
  const [lanes, setLanes] = useState<StreamLane[]>([]);
  const [transcript, setTranscript] = useState<TranscriptMessage[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [cmdMenuOpen, setCmdMenuOpen] = useState(false);
  const [filterSpeaker, setFilterSpeaker] = useState('');
  const [filterRecipient, setFilterRecipient] = useState('');
  const [presetByEntitySlug, setPresetByEntitySlug] = useState<
    Readonly<Record<string, string | null>>
  >({});
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const streamFiltersRef = useRef<Map<string, AgentThinkingStreamFilter>>(new Map());

  async function fetchTranscript(): Promise<TranscriptMessage[]> {
    try {
      const res = await api<{ items: TranscriptMessage[] }>(
        `/workspaces/${encodeURIComponent(workspaceId)}/composer/messages`,
      );
      return res.items;
    } catch {
      return [];
    }
  }

  async function reloadTranscript() {
    const items = await fetchTranscript();
    setTranscript((prev) => reconcileTranscript(items, prev));
  }

  useEffect(() => {
    void reloadTranscript();
  }, [workspaceId]);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcript, lanes]);

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

  const speakerOptions = useMemo(() => {
    const users = new Set<string>();
    let hasUser = false;
    let hasAssistant = false;
    let hasSystem = false;
    for (const msg of transcript) {
      if (msg.role === 'user') {
        hasUser = true;
        if (msg.author_username) users.add(msg.author_username);
      } else if (msg.role === 'assistant') {
        hasAssistant = true;
      } else if (msg.role === 'system') {
        hasSystem = true;
      }
    }
    return { users: [...users].sort(), hasUser, hasAssistant, hasSystem };
  }, [transcript]);

  const recipientOptions = useMemo(() => {
    const set = new Set<string>();
    for (const msg of transcript) {
      if (msg.target_entity) set.add(msg.target_entity);
    }
    for (const lane of lanes) {
      if (lane.target) set.add(lane.target);
    }
    return [...set].sort();
  }, [transcript, lanes]);

  const filteredTranscript = useMemo(() => {
    return transcript.filter((msg) => {
      if (msg.role === 'assistant' && msg.turn_id) {
        if (lanes.some((lane) => lane.turnId === msg.turn_id && lane.status === 'responding')) {
          return false;
        }
      }
      if (filterRecipient && msg.target_entity !== filterRecipient) return false;
      if (filterSpeaker) {
        if (filterSpeaker === '__user__') return msg.role === 'user';
        if (filterSpeaker === '__assistant__') return msg.role === 'assistant';
        if (filterSpeaker === '__system__') return msg.role === 'system';
        if (msg.role === 'user') return msg.author_username === filterSpeaker;
        if (msg.role === 'assistant') return msg.target_entity === filterSpeaker;
        return false;
      }
      return true;
    });
  }, [transcript, lanes, filterSpeaker, filterRecipient]);

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
    streamFiltersRef.current.clear();
    try {
      const result = await api<MessageSendResult>('/messaging/messages', {
        method: 'POST',
        body: JSON.stringify({ turn_text: text, workspace_id: workspaceId }),
      });
      setDeliveryRows(result.results);
      setText('');
      await reloadTranscript();

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
          turnIds.map((item) => ({
            turnId: item.turnId,
            target: item.target,
            status: 'responding',
            text: '',
            thinking: '',
          })),
        );
        await Promise.all(
          turnIds.map(async ({ turnId, target }) => {
            const filter = new AgentThinkingStreamFilter();
            streamFiltersRef.current.set(turnId, filter);
            let rawAccum = '';
            try {
              await streamComposerTurn(
                workspaceId,
                turnId,
                token,
                (frame) => {
                  setLanes((prev) => {
                    const next = prev.map((lane) => {
                      if (lane.turnId !== turnId) return lane;
                      if (frame.type === 'chat.response.chunk' && frame.token) {
                        rawAccum += frame.token;
                        const visible = showThinkingChain
                          ? rawAccum
                          : filter.feed(frame.token);
                        const thinking = showThinkingChain
                          ? extractThinkingBlocks(rawAccum)
                          : '';
                        return {
                          ...lane,
                          status: 'responding' as const,
                          text: showThinkingChain
                            ? stripAgentThinkingBlocks(rawAccum) || visible
                            : lane.text + visible,
                          thinking,
                        };
                      }
                      if (frame.type === 'chat.response.done') {
                        const finalRaw =
                          typeof frame.text === 'string' && frame.text.length > 0
                            ? frame.text
                            : rawAccum || lane.text;
                        const flushed = showThinkingChain ? '' : filter.flush();
                        const body = showThinkingChain
                          ? stripAgentThinkingBlocks(finalRaw)
                          : stripAgentThinkingBlocks(finalRaw) || lane.text + flushed;
                        return {
                          ...lane,
                          status: 'completed' as const,
                          text: body,
                          thinking: extractThinkingBlocks(finalRaw),
                        };
                      }
                      if (frame.type === 'chat.response.error') {
                        return {
                          ...lane,
                          status: 'failed' as const,
                          error: frame.message ?? t('composer.instanceOffline'),
                        };
                      }
                      return lane;
                    });
                    const updated = next.find((l) => l.turnId === turnId);
                    if (
                      updated &&
                      (updated.status === 'completed' || updated.status === 'failed')
                    ) {
                      setTranscript((tr) => upsertAssistantBubble(tr, updated));
                    }
                    return next;
                  });
                },
                ac.signal,
              );
            } catch (e) {
              if (ac.signal.aborted) return;
              const failedLane: StreamLane = {
                turnId,
                target,
                status: 'failed',
                text: '',
                thinking: '',
                error: e instanceof Error ? e.message : t('composer.streamFailed'),
              };
              setLanes((prev) =>
                prev.map((lane) => (lane.turnId === turnId ? failedLane : lane)),
              );
              setTranscript((tr) => upsertAssistantBubble(tr, failedLane));
            }
          }),
        );
        // Wait briefly so finalize can commit, then reconcile without wiping local text.
        await new Promise((r) => setTimeout(r, 250));
        const server = await fetchTranscript();
        setTranscript((prev) => reconcileTranscript(server, prev));
        setLanes([]);
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

  const textareaHeight = compact ? 'h-28' : 'h-40';

  return (
    <section
      className={`flex h-full flex-col ${compact ? 'p-3' : 'p-6'}`}
      aria-label={t('composer.title')}
    >
      <header className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {!compact ? (
            <>
              <MessageSquare className="size-5 text-slate-700" aria-hidden="true" />
              <h2 className="text-lg font-semibold text-slate-900">{t('composer.title')}</h2>
            </>
          ) : (
            <span className="text-xs font-semibold text-slate-700">{t('composer.title')}</span>
          )}
        </div>
        <button
          type="button"
          onClick={() => setSettingsOpen((v) => !v)}
          className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs ${
            settingsOpen
              ? 'bg-slate-200 text-slate-900'
              : 'text-slate-500 hover:bg-slate-100 hover:text-slate-800'
          }`}
          aria-expanded={settingsOpen}
          aria-label={t('composer.settingsTitle')}
        >
          <Settings className="size-3.5" aria-hidden="true" />
          {t('composer.settings')}
        </button>
      </header>

      {settingsOpen ? (
        <div className="mb-2 space-y-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-800">
          <p className="font-semibold text-slate-900">{t('composer.settingsTitle')}</p>
          <label className="flex items-center justify-between gap-3">
            <span>{t('composer.settingShowThinking')}</span>
            <input
              type="checkbox"
              checked={showThinkingChain}
              onChange={(e) => setShowThinkingChain(e.target.checked)}
            />
          </label>
          <label className="flex items-center justify-between gap-3">
            <span>{t('composer.settingRenderMarkdown')}</span>
            <input
              type="checkbox"
              checked={renderMd}
              onChange={(e) => setRenderMarkdown(e.target.checked)}
            />
          </label>
        </div>
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

      <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-600">
        <label className="inline-flex items-center gap-1">
          <span>{t('composer.filterSpeaker')}</span>
          <select
            value={filterSpeaker}
            onChange={(e) => setFilterSpeaker(e.target.value)}
            className="rounded border border-slate-300 bg-white px-1.5 py-0.5 text-slate-800"
          >
            <option value="">{t('composer.filterAll')}</option>
            {speakerOptions.hasUser ? (
              <option value="__user__">{t('composer.roleUser')}</option>
            ) : null}
            {speakerOptions.users.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
            {speakerOptions.hasAssistant ? (
              <option value="__assistant__">{t('composer.roleAssistant')}</option>
            ) : null}
            {speakerOptions.hasSystem ? (
              <option value="__system__">{t('composer.roleSystem')}</option>
            ) : null}
          </select>
        </label>
        <label className="inline-flex items-center gap-1">
          <span>{t('composer.filterRecipient')}</span>
          <select
            value={filterRecipient}
            onChange={(e) => setFilterRecipient(e.target.value)}
            className="rounded border border-slate-300 bg-white px-1.5 py-0.5 text-slate-800"
          >
            <option value="">{t('composer.filterAll')}</option>
            {recipientOptions.map((slug) => (
              <option key={slug} value={slug}>
                @{slug}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mb-2 min-h-0 flex-1 space-y-2 overflow-y-auto rounded-lg border border-slate-200 bg-white p-2">
        {filteredTranscript.length === 0 && lanes.length === 0 ? (
          <p className="px-1 py-6 text-center text-xs text-slate-400">{t('composer.transcriptEmpty')}</p>
        ) : null}
        {filteredTranscript.map((msg) => (
          <MessageBubble
            key={msg.id}
            role={msg.role}
            target={msg.target_entity}
            content={msg.content}
            status={msg.status}
            authorUsername={msg.author_username ?? null}
            showThinking={showThinkingChain}
            renderMd={renderMd}
          />
        ))}
        {lanes
          .filter((lane) => {
            if (filterRecipient && lane.target !== filterRecipient) return false;
            if (filterSpeaker && filterSpeaker !== '__assistant__') {
              if (filterSpeaker === '__user__' || filterSpeaker === '__system__') return false;
              if (filterSpeaker !== lane.target) return false;
            }
            return true;
          })
          .map((lane) => (
            <div
              key={lane.turnId}
              className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-2 py-1.5 text-xs"
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="text-[10px] text-slate-500">
                  {t('composer.roleAssistant')}
                  <code className="ml-1 font-mono text-slate-700">@{lane.target}</code>
                </span>
                <StatusBadge status={lane.status} />
              </div>
              {showThinkingChain && lane.thinking ? (
                <ThinkingBlock text={lane.thinking} />
              ) : null}
              <MessageBody
                text={lane.text || (lane.status === 'responding' ? '…' : '')}
                renderMd={renderMd}
              />
              {lane.error ? <p className="mt-1 text-red-700">{lane.error}</p> : null}
            </div>
          ))}
        <div ref={transcriptEndRef} />
      </div>

      {deliveryRows.length > 0 ? (
        <ul className="mb-2 max-h-16 overflow-y-auto text-xs text-slate-700">
          {deliveryRows.flatMap((row) =>
            row.delivery.map((d, i) => {
              if (d.delivered) return null;
              const reasonLabel =
                d.reason === 'routed_to_cerebellum'
                  ? t('composer.routedToCerebellum')
                  : (d.reason ?? t('composer.blocked'));
              return (
                <li key={`${row.target_entity}-${i}`} className="font-mono">
                  @{row.target_entity ?? '?'}: {reasonLabel}
                </li>
              );
            }),
          )}
        </ul>
      ) : null}

      <div className="relative shrink-0">
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
        <ul className="mt-2 max-h-16 overflow-y-auto text-xs text-slate-600">
          {compartments.map((c) => (
            <li key={c.label} className="truncate font-mono">
              {c.label === 'general' ? t('composer.compartmentGeneral') : `@${c.label}`}
              :{' '}
              {c.directives.length > 0
                ? c.directives.map((d) => d.cmd || d.args.join(' ') || '(chat)').join(', ')
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

function ThinkingBlock({ text }: { readonly text: string }) {
  const { t } = useTranslation();
  return (
    <details className="mb-1 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-900">
      <summary className="cursor-pointer select-none font-medium">{t('composer.thinkingLabel')}</summary>
      <pre className="mt-1 whitespace-pre-wrap break-words font-sans opacity-90">{text}</pre>
    </details>
  );
}

function MessageBody({ text, renderMd }: { readonly text: string; readonly renderMd: boolean }) {
  if (!text) return null;
  if (renderMd) {
    return (
      <div
        className="composer-markdown prose prose-sm max-w-none break-words text-slate-800"
        // nodeskclaw-style sanitized HTML
        dangerouslySetInnerHTML={{ __html: renderMarkdown(text) }}
      />
    );
  }
  return <pre className="whitespace-pre-wrap break-words font-sans text-slate-800">{text}</pre>;
}

function MessageBubble({
  role,
  target,
  content,
  status,
  authorUsername,
  showThinking,
  renderMd,
}: {
  readonly role: string;
  readonly target: string | null;
  readonly content: string;
  readonly status: string;
  readonly authorUsername: string | null;
  readonly showThinking: boolean;
  readonly renderMd: boolean;
}) {
  const { t } = useTranslation();
  const thinking = role === 'assistant' && showThinking ? extractThinkingBlocks(content) : '';
  const body = role === 'assistant' ? stripAgentThinkingBlocks(content) : content;
  const tone =
    role === 'user'
      ? 'bg-blue-50 text-slate-800'
      : role === 'assistant'
        ? 'bg-slate-50 text-slate-800'
        : 'bg-amber-50 text-amber-900';
  const speaker =
    role === 'user'
      ? authorUsername || t('composer.roleUser')
      : role === 'assistant'
        ? t('composer.roleAssistant')
        : t('composer.roleSystem');
  return (
    <div className={`rounded-lg px-2 py-1.5 text-xs ${tone}`}>
      <div className="mb-0.5 flex items-center justify-between gap-2 text-[10px] text-slate-500">
        <span>
          <span className="font-medium text-slate-700">{speaker}</span>
          {target ? (
            <>
              <span className="mx-1 text-slate-400">→</span>
              <code className="font-mono text-slate-700">@{target}</code>
            </>
          ) : null}
        </span>
        {status === 'responding' ? (
          <span className="text-amber-700">{t('composer.statusResponding')}</span>
        ) : null}
      </div>
      {thinking ? <ThinkingBlock text={thinking} /> : null}
      <MessageBody text={body || (status === 'responding' ? '…' : '')} renderMd={renderMd} />
    </div>
  );
}
