import { AlertCircle, Hash, LoaderCircle, MessageSquare, Send, Settings } from 'lucide-react';
import { type KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityBlock } from '@/components/ActivityBlock';
import { CommandAutocomplete } from '@/components/CommandAutocomplete';
import { type IntroduceTarget, MentionAutocomplete } from '@/components/MentionAutocomplete';
import {
  AgentThinkingStreamFilter,
  extractThinkingBlocks,
  stripAgentThinkingBlocks,
} from '@/lib/agentOutput';
import { api } from '@/lib/api';
import { introduceEntityIntoWorkspace } from '@/lib/api/instances';
import { resolveError } from '@/lib/apiError';
import {
  isCursorOnFirstLine,
  isCursorOnLastLine,
  useComposerCommandHistory,
} from '@/lib/composerHistory';
import { streamComposerTurn } from '@/lib/composerStream';
import {
  buildOptimisticUserBubbles,
  ingestActivityFrame,
  reconcileTranscript,
  type StreamLane,
  type TranscriptMessage,
  upsertAssistantBubble,
  userDisplayLabel,
} from '@/lib/composerTranscript';
import { renderMarkdown } from '@/lib/markdown';
import {
  type Compartment,
  parse_turn,
  SlashParserError,
  segmentCompartments,
  type Turn,
} from '@/lib/slash-parser';
import { cn } from '@/lib/utils';
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

type ComposerPanelProps = {
  readonly workspaceId: string;
  readonly compact?: boolean;
};

function directiveDisplayText(target: string | null, turn: Turn | null, fallback: string): string {
  if (turn === null) return fallback;
  const match = turn.directives.find((d) => d.target_entity === target);
  if (match === undefined) return fallback;
  if (match.raw_text.trim()) return match.raw_text.trim();
  const body = [match.cmd, ...match.args].filter(Boolean).join(' ').trim();
  return body || fallback;
}

export default function ComposerPanel({ workspaceId, compact = false }: ComposerPanelProps) {
  const { t } = useTranslation();
  const token = useSessionStore((s) => s.token);
  const currentUsername = useSessionStore((s) => s.user?.username ?? null);
  const currentNickname = useSessionStore((s) => s.user?.nickname ?? null);
  // Human label: nickname → username (aligned with Lost One display_name → slug).
  const currentDisplayName = userDisplayLabel(currentNickname, currentUsername) || null;
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
  const [mentionMenuOpen, setMentionMenuOpen] = useState(false);
  const [filterSpeaker, setFilterSpeaker] = useState('');
  const [filterRecipient, setFilterRecipient] = useState('');
  const [entityNameBySlug, setEntityNameBySlug] = useState<Readonly<Record<string, string>>>({});
  const [presetByEntitySlug, setPresetByEntitySlug] = useState<
    Readonly<Record<string, string | null>>
  >({});
  const [introduceTarget, setIntroduceTarget] = useState<IntroduceTarget | null>(null);
  const [introducing, setIntroducing] = useState(false);
  const [introduceError, setIntroduceError] = useState<string | null>(null);
  const [mentionRefreshKey, setMentionRefreshKey] = useState(0);
  const [activeSegment, setActiveSegment] = useState<string>('general');
  const [segmentInputs, setSegmentInputs] = useState<Record<string, string>>({
    general: '',
  });
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const streamFiltersRef = useRef<Map<string, AgentThinkingStreamFilter>>(new Map());
  const commandHistory = useComposerCommandHistory(workspaceId);

  const entityLabel = useCallback(
    (slug: string | null | undefined, fallbackName?: string | null): string => {
      if (!slug) return fallbackName?.trim() || '';
      const fromMap = entityNameBySlug[slug];
      if (fromMap?.trim()) return fromMap.trim();
      if (fallbackName?.trim()) return fallbackName.trim();
      return slug;
    },
    [entityNameBySlug],
  );

  const fetchTranscript = useCallback(async (): Promise<TranscriptMessage[]> => {
    try {
      const params = new URLSearchParams();
      if (filterSpeaker) params.set('speaker', filterSpeaker);
      if (filterRecipient) params.set('recipient', filterRecipient);
      const qs = params.toString();
      const path = `/workspaces/${encodeURIComponent(workspaceId)}/composer/messages${
        qs ? `?${qs}` : ''
      }`;
      const res = await api<{ items: TranscriptMessage[] }>(path);
      return res.items;
    } catch {
      return [];
    }
  }, [filterSpeaker, filterRecipient, workspaceId]);

  const reloadTranscript = useCallback(
    async (mode: 'merge' | 'replace' = 'merge') => {
      const items = await fetchTranscript();
      if (mode === 'replace') {
        setTranscript(items);
        return;
      }
      setTranscript((prev) => reconcileTranscript(items, prev));
    },
    [fetchTranscript],
  );

  useEffect(() => {
    void reloadTranscript('replace');
  }, [reloadTranscript]);

  useEffect(() => {
    const names: Record<string, string> = {};
    for (const msg of transcript) {
      if (msg.target_entity && msg.target_entity_name?.trim()) {
        names[msg.target_entity] = msg.target_entity_name.trim();
      }
    }
    if (Object.keys(names).length === 0) return;
    setEntityNameBySlug((prev) => ({ ...prev, ...names }));
  }, [transcript]);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

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
    void api<{ items: { slug: string; name: string; preset_slug: string | null }[] }>(
      `/workspaces/${encodeURIComponent(workspaceId)}/mention-candidates`,
    )
      .then((res) => {
        if (cancelled) return;
        const presets: Record<string, string | null> = {};
        const names: Record<string, string> = {};
        for (const item of res.items) {
          presets[item.slug] = item.preset_slug;
          if (item.name?.trim()) names[item.slug] = item.name.trim();
        }
        setPresetByEntitySlug(presets);
        setEntityNameBySlug((prev) => ({ ...prev, ...names }));
      })
      .catch(() => {
        if (!cancelled) {
          setPresetByEntitySlug({});
        }
      });
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

  useEffect(() => {
    if (compartments.length === 0) return;
    const labels = compartments.map((c) => c.label);
    if (!labels.includes(activeSegment)) {
      setActiveSegment(labels[0]);
    }
  }, [compartments, activeSegment]);

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
    const users = new Map<string, string>(); // username -> display label
    const entities = new Map<string, string>(); // slug -> label
    let hasSystem = false;
    for (const msg of transcript) {
      if (msg.role === 'user' && msg.author_username) {
        users.set(
          msg.author_username,
          userDisplayLabel(msg.author_nickname, msg.author_username) ||
            msg.author_display_name?.trim() ||
            msg.author_username,
        );
      } else if (msg.role === 'assistant' && msg.target_entity) {
        entities.set(
          msg.target_entity,
          msg.target_entity_name?.trim() || entityLabel(msg.target_entity),
        );
      } else if (msg.role === 'system') {
        hasSystem = true;
      }
    }
    for (const lane of lanes) {
      if (lane.target) {
        entities.set(lane.target, entityLabel(lane.target, lane.targetName));
      }
    }
    return {
      users: [...users.entries()].sort((a, b) => a[1].localeCompare(b[1])),
      entities: [...entities.entries()].sort((a, b) => a[1].localeCompare(b[1])),
      hasSystem,
    };
  }, [transcript, lanes, entityLabel]);

  const recipientOptions = useMemo(() => {
    const users = new Map<string, string>();
    const entities = new Map<string, string>();
    for (const msg of transcript) {
      if (msg.role === 'user' && msg.target_entity) {
        entities.set(
          msg.target_entity,
          msg.target_entity_name?.trim() || entityLabel(msg.target_entity),
        );
      } else if (msg.role === 'assistant') {
        const username = msg.recipient_username;
        if (username) {
          users.set(
            username,
            userDisplayLabel(msg.recipient_nickname, username) ||
              msg.recipient_display_name?.trim() ||
              username,
          );
        }
      }
    }
    for (const lane of lanes) {
      if (lane.target) {
        entities.set(lane.target, entityLabel(lane.target, lane.targetName));
      }
      if (lane.recipientUsername) {
        users.set(
          lane.recipientUsername,
          lane.recipientDisplayName ||
            (lane.recipientUsername === currentUsername ? currentDisplayName : null) ||
            lane.recipientUsername,
        );
      }
    }
    if (currentUsername) {
      users.set(currentUsername, currentDisplayName || currentUsername);
    }
    return {
      users: [...users.entries()].sort((a, b) => a[1].localeCompare(b[1])),
      entities: [...entities.entries()].sort((a, b) => a[1].localeCompare(b[1])),
    };
  }, [transcript, lanes, currentUsername, currentDisplayName, entityLabel]);

  const filteredTranscript = useMemo(() => {
    // Speaker/recipient filters are applied server-side on reload.
    // Only hide in-flight assistant rows that are mirrored by live lanes.
    return transcript.filter((msg) => {
      if (msg.role === 'assistant' && msg.turn_id) {
        if (lanes.some((lane) => lane.turnId === msg.turn_id && lane.status === 'responding')) {
          return false;
        }
      }
      return true;
    });
  }, [transcript, lanes]);

  const bareEmployeeCmdHint = useMemo(() => {
    if (turn === null) return false;
    for (const d of turn.directives) {
      if (
        d.target_entity === null &&
        d.cmd &&
        !['/read', '/list', '/write', '/archive'].includes(d.cmd)
      ) {
        if (
          [
            '/interrupt',
            '/pause',
            '/resume',
            '/status',
            '/snapshot',
            '/distill',
            '/consolidate',
            '/reflect',
          ].includes(d.cmd)
        ) {
          return true;
        }
        if (!GLOBAL_LIKE.has(d.cmd)) return true;
      }
    }
    return false;
  }, [turn]);

  const canSend = text.trim().length > 0 && parseError === null && !sending && !introducing;

  async function handleIntroduceConfirm() {
    if (introduceTarget === null || introducing) return;
    setIntroducing(true);
    setIntroduceError(null);
    try {
      await introduceEntityIntoWorkspace(workspaceId, introduceTarget.entity_id);
      const slug = introduceTarget.slug;
      const textarea = textareaRef.current;
      if (textarea !== null) {
        const pos = textarea.selectionStart;
        const inserted = `@${slug} `;
        const newText = text.slice(0, pos) + inserted + text.slice(pos);
        const newCursor = pos + inserted.length;
        setText(newText);
        requestAnimationFrame(() => {
          textarea.focus();
          textarea.setSelectionRange(newCursor, newCursor);
        });
      } else {
        setText((prev) => `${prev}@${slug} `);
      }
      setMentionRefreshKey((k) => k + 1);
      setIntroduceTarget(null);
    } catch (e) {
      setIntroduceError(resolveError(t, e, 'workspace.introduceFailed'));
    } finally {
      setIntroducing(false);
    }
  }

  function handleIntroduceCancel() {
    setIntroduceTarget(null);
    setIntroduceError(null);
  }

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
    const outgoing = text;
    const outgoingTurn = turn;
    try {
      const result = await api<MessageSendResult>('/messaging/messages', {
        method: 'POST',
        body: JSON.stringify({ turn_text: outgoing, workspace_id: workspaceId }),
      });
      setDeliveryRows(result.results);
      commandHistory.commit(outgoing);
      setText('');

      const turnIds: {
        turnId: string;
        target: string;
        targetName: string;
        content: string;
      }[] = [];
      for (const row of result.results) {
        for (const d of row.delivery) {
          if (d.delivered && d.turn_id) {
            const target = row.target_entity ?? d.instance_id ?? 'unknown';
            turnIds.push({
              turnId: d.turn_id,
              target,
              targetName: entityLabel(target),
              content: directiveDisplayText(row.target_entity, outgoingTurn, outgoing),
            });
          }
        }
      }

      // Immediate independent user bubbles (do not wait for reload / stream).
      if (turnIds.length > 0) {
        setTranscript((prev) => [
          ...prev,
          ...buildOptimisticUserBubbles(
            turnIds.map((item) => ({
              turnId: item.turnId,
              target: item.target,
              targetName: item.targetName,
              content: item.content,
              authorUsername: currentUsername,
              authorNickname: currentNickname,
            })),
          ),
        ]);
      } else {
        await reloadTranscript();
      }

      if (turnIds.length > 0) {
        setLanes(
          turnIds.map((item) => ({
            turnId: item.turnId,
            target: item.target,
            targetName: item.targetName,
            recipientUsername: currentUsername,
            recipientDisplayName: currentDisplayName,
            status: 'responding',
            text: '',
            thinking: '',
            activities: [],
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
                        const visible = showThinkingChain ? rawAccum : filter.feed(frame.token);
                        const thinking = showThinkingChain ? extractThinkingBlocks(rawAccum) : '';
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
                      if (frame.type === 'chat.response.activity' && frame.kind) {
                        return {
                          ...lane,
                          activities: ingestActivityFrame(lane.activities, {
                            kind: frame.kind,
                            status: frame.status ?? 'delta',
                            tool_name: frame.tool_name,
                            delta: frame.delta,
                          }),
                        };
                      }
                      return lane;
                    });
                    const updated = next.find((l) => l.turnId === turnId);
                    if (updated) {
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
                activities: [],
                error: e instanceof Error ? e.message : t('composer.streamFailed'),
              };
              setLanes((prev) => prev.map((lane) => (lane.turnId === turnId ? failedLane : lane)));
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
      setSendError(resolveError(t, e, 'composer.sendFailed'));
    } finally {
      setSending(false);
    }
  }

  function handleSegmentSend(segmentLabel: string) {
    const input = (segmentInputs[segmentLabel] ?? '').trim();
    if (input.length === 0 || sending || introducing) return;
    const prefix = segmentLabel === 'general' ? '' : `@${segmentLabel} `;
    const outgoing = `${prefix}${input}`;
    setText((prev) => {
      const sep = prev.trim().length > 0 ? '\n' : '';
      return `${prev}${sep}${outgoing}`;
    });
    setSegmentInputs((prev) => ({ ...prev, [segmentLabel]: '' }));
    requestAnimationFrame(() => {
      textareaRef.current?.focus();
    });
  }

  function applyRecalled(next: string) {
    setText(next);
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (el !== null) {
        el.focus();
        el.setSelectionRange(next.length, next.length);
      }
    });
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      void handleSend();
      return;
    }
    if (e.nativeEvent.isComposing) return;
    if (cmdMenuOpen || mentionMenuOpen) return;

    const cursor = e.currentTarget.selectionStart;
    if (e.key === 'ArrowUp') {
      if (!isCursorOnFirstLine(text, cursor)) return;
      const recalled = commandHistory.older(text);
      if (recalled.action === 'ignore') return;
      e.preventDefault();
      if (recalled.action === 'apply') applyRecalled(recalled.text);
      return;
    }
    if (e.key === 'ArrowDown') {
      if (!commandHistory.isBrowsing()) return;
      if (!isCursorOnLastLine(text, cursor)) return;
      const recalled = commandHistory.newer();
      if (recalled.action === 'ignore') return;
      e.preventDefault();
      if (recalled.action === 'apply') applyRecalled(recalled.text);
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
            {speakerOptions.users.map(([username, label]) => (
              <option key={`user:${username}`} value={`user:${username}`}>
                {label}
                {currentUsername === username ? ` ${t('composer.youSuffix')}` : ''}
              </option>
            ))}
            {speakerOptions.entities.map(([slug, label]) => (
              <option key={`entity:${slug}`} value={`entity:${slug}`}>
                {label}
              </option>
            ))}
            {speakerOptions.hasSystem ? (
              <option value="system">{t('composer.roleSystem')}</option>
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
            {recipientOptions.users.map(([username, label]) => (
              <option key={`user:${username}`} value={`user:${username}`}>
                {label}
                {currentUsername === username ? ` ${t('composer.youSuffix')}` : ''}
              </option>
            ))}
            {recipientOptions.entities.map(([slug, label]) => (
              <option key={`entity:${slug}`} value={`entity:${slug}`}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mb-2 min-h-0 flex-1 space-y-2 overflow-y-auto rounded-lg border border-slate-200 bg-white p-2">
        {filteredTranscript.length === 0 && lanes.length === 0 ? (
          <p className="px-1 py-6 text-center text-xs text-slate-400">
            {t('composer.transcriptEmpty')}
          </p>
        ) : null}
        {filteredTranscript.map((msg) => (
          <MessageBubble
            key={msg.id}
            role={msg.role}
            target={msg.target_entity}
            targetName={msg.target_entity_name ?? entityLabel(msg.target_entity)}
            content={msg.content}
            status={msg.status}
            authorUsername={msg.author_username ?? null}
            authorDisplayName={
              msg.author_display_name ||
              userDisplayLabel(msg.author_nickname, msg.author_username) ||
              null
            }
            recipientUsername={msg.recipient_username ?? currentUsername}
            recipientDisplayName={
              msg.recipient_display_name ||
              userDisplayLabel(msg.recipient_nickname, msg.recipient_username) ||
              currentDisplayName
            }
            currentUsername={currentUsername}
            showThinking={showThinkingChain}
            renderMd={renderMd}
          />
        ))}
        {lanes
          .filter((lane) => {
            if (filterRecipient) {
              // Live lanes are always Lost One → human replies.
              if (filterRecipient.startsWith('entity:')) return false;
              if (filterRecipient.startsWith('user:')) {
                const want = filterRecipient.slice('user:'.length);
                if ((lane.recipientUsername || currentUsername) !== want) return false;
              }
            }
            if (filterSpeaker) {
              if (filterSpeaker === 'system') return false;
              if (filterSpeaker.startsWith('user:')) return false;
              if (filterSpeaker.startsWith('entity:')) {
                if (lane.target !== filterSpeaker.slice('entity:'.length)) return false;
              }
            }
            return true;
          })
          .map((lane) => (
            <div
              key={lane.turnId}
              className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-2 py-1.5 text-xs"
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <PartyArrow
                  speaker={entityLabel(lane.target, lane.targetName)}
                  recipient={
                    lane.recipientDisplayName ||
                    (lane.recipientUsername === currentUsername ? currentDisplayName : null) ||
                    lane.recipientUsername ||
                    currentDisplayName ||
                    t('composer.roleUser')
                  }
                  recipientIsYou={
                    Boolean(currentUsername) &&
                    (lane.recipientUsername || currentUsername) === currentUsername
                  }
                />
                <StatusBadge status={lane.status} />
              </div>
              {showThinkingChain && lane.thinking ? <ThinkingBlock text={lane.thinking} /> : null}
              <ActivityBlock activities={lane.activities} />
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
            row.delivery.map((d) => {
              if (d.delivered) return null;
              const reasonLabel =
                d.reason === 'routed_to_cerebellum'
                  ? t('composer.routedToCerebellum')
                  : (d.reason ?? t('composer.blocked'));
              return (
                <li
                  key={`${row.target_entity ?? 'none'}-${d.reason ?? 'blocked'}`}
                  className="font-mono"
                >
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
          onOpenChange={setMentionMenuOpen}
          onIntroduceRequest={(entity) => {
            setIntroduceError(null);
            setIntroduceTarget(entity);
          }}
          refreshKey={mentionRefreshKey}
        />
      </div>

      {compartments.length > 0 ? (
        <div
          className="mt-2 rounded-lg border border-slate-200 bg-white"
          data-testid="segment-panel"
        >
          <div
            role="tablist"
            aria-label={t('composer.segment.general')}
            className="flex flex-wrap items-center gap-1 border-b border-slate-200 bg-slate-50 px-2 py-1.5"
          >
            {compartments.map((c) => {
              const isActive = activeSegment === c.label;
              const label =
                c.label === 'general'
                  ? t('composer.segment.general')
                  : entityLabel(c.label, c.label);
              const directiveCount = c.directives.length;
              return (
                <button
                  key={c.label}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  tabIndex={isActive ? 0 : -1}
                  onClick={() => setActiveSegment(c.label)}
                  data-testid={`segment-tab-${c.label}`}
                  className={cn(
                    'inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500',
                    isActive
                      ? 'bg-white text-slate-900 shadow-sm'
                      : 'text-slate-600 hover:bg-white hover:text-slate-900',
                  )}
                >
                  {c.label !== 'general' ? (
                    <Hash className="size-3 shrink-0 text-slate-400" aria-hidden="true" />
                  ) : null}
                  <span>{label}</span>
                  {directiveCount > 0 ? (
                    <span className="rounded-full bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                      {directiveCount}
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>

          <div className="p-2" role="tabpanel" data-testid={`segment-content-${activeSegment}`}>
            {(() => {
              const active = compartments.find((c) => c.label === activeSegment);
              if (active === undefined) return null;

              const items: { key: string; content: React.ReactNode }[] = [];

              if (active.directives.length > 0) {
                for (const d of active.directives) {
                  const display =
                    d.raw_text.trim() ||
                    [d.cmd, ...d.args].filter(Boolean).join(' ').trim() ||
                    t('composer.segment.chatLabel');
                  items.push({
                    key: `dir-${d.cmd}-${d.args.join('-')}`,
                    content: (
                      <div
                        key={`dir-${d.cmd}-${d.args.join('-')}`}
                        className="truncate rounded bg-slate-50 px-2 py-1 font-mono text-xs text-slate-700"
                      >
                        {display}
                      </div>
                    ),
                  });
                }
              } else if (active.general_text !== null && active.label === 'general') {
                items.push({
                  key: 'general-text',
                  content: (
                    <p key="general-text" className="truncate px-1 text-xs text-slate-500">
                      {active.general_text}
                    </p>
                  ),
                });
              } else {
                items.push({
                  key: 'empty',
                  content: (
                    <p key="empty" className="px-1 text-xs text-slate-400">
                      {t('composer.segment.noDirectives')}
                    </p>
                  ),
                });
              }

              return (
                <div className="mb-2 space-y-1">
                  {items.map((item) => (
                    <div key={item.key}>{item.content}</div>
                  ))}
                </div>
              );
            })()}

            <div className="flex items-center gap-1.5">
              <input
                type="text"
                value={segmentInputs[activeSegment] ?? ''}
                onChange={(e) =>
                  setSegmentInputs((prev) => ({ ...prev, [activeSegment]: e.target.value }))
                }
                onKeyDown={(e) => {
                  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                    e.preventDefault();
                    handleSegmentSend(activeSegment);
                  }
                }}
                placeholder={
                  activeSegment === 'general'
                    ? t('composer.segment.inputPlaceholderGeneral')
                    : t('composer.segment.inputPlaceholder', {
                        name: entityLabel(activeSegment, activeSegment),
                      })
                }
                className="flex-1 rounded border border-slate-300 px-2 py-1 font-mono text-xs text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                aria-label={
                  activeSegment === 'general'
                    ? t('composer.segment.sendGeneral')
                    : t('composer.segment.sendToSegment', {
                        name: entityLabel(activeSegment, activeSegment),
                      })
                }
                data-testid={`segment-input-${activeSegment}`}
              />
              <button
                type="button"
                onClick={() => handleSegmentSend(activeSegment)}
                disabled={
                  sending || introducing || (segmentInputs[activeSegment] ?? '').trim().length === 0
                }
                className="inline-flex items-center rounded bg-blue-600 px-2 py-1 text-xs font-semibold text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
                aria-label={
                  activeSegment === 'general'
                    ? t('composer.segment.sendGeneral')
                    : t('composer.segment.sendToSegment', {
                        name: entityLabel(activeSegment, activeSegment),
                      })
                }
                data-testid={`segment-send-${activeSegment}`}
              >
                <Send className="size-3" aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
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

      {introduceTarget !== null ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="introduce-confirm-title"
          className="fixed inset-0 z-[60] flex items-end justify-center bg-slate-950/50 p-0 sm:items-center sm:p-4"
        >
          <div className="flex w-full max-w-md flex-col overflow-hidden rounded-t-xl border border-slate-200 bg-white shadow-2xl sm:rounded-xl">
            <header className="border-b border-slate-200 px-5 py-4">
              <h2 id="introduce-confirm-title" className="text-base font-semibold text-slate-950">
                {t('workspace.introduceTitle')}
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                {t('composer.introduceConfirm', { name: introduceTarget.name })}
              </p>
            </header>
            {introduceError !== null ? (
              <div
                role="alert"
                className="mx-5 mt-3 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
              >
                <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
                <p>{introduceError}</p>
              </div>
            ) : null}
            <footer className="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3">
              <button
                type="button"
                onClick={handleIntroduceCancel}
                disabled={introducing}
                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                disabled={introducing}
                onClick={() => void handleIntroduceConfirm()}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {introducing ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                ) : null}
                {t('workspace.introduceSubmit')}
              </button>
            </footer>
          </div>
        </div>
      ) : null}
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
      <summary className="cursor-pointer select-none font-medium">
        {t('composer.thinkingLabel')}
      </summary>
      <pre className="mt-1 whitespace-pre-wrap break-words font-sans opacity-90">{text}</pre>
    </details>
  );
}

function PartyArrow({
  speaker,
  recipient,
  speakerIsYou = false,
  recipientIsYou = false,
}: {
  readonly speaker: string;
  readonly recipient: string | null;
  readonly speakerIsYou?: boolean;
  readonly recipientIsYou?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <span className="text-[10px] text-slate-500">
      <span className="font-medium text-slate-700">{speaker}</span>
      {speakerIsYou ? (
        <span className="ml-0.5 text-slate-400">{t('composer.youSuffix')}</span>
      ) : null}
      {recipient ? (
        <>
          <span className="mx-1 text-slate-400">→</span>
          <span className="font-medium text-slate-700">{recipient}</span>
          {recipientIsYou ? (
            <span className="ml-0.5 text-slate-400">{t('composer.youSuffix')}</span>
          ) : null}
        </>
      ) : null}
    </span>
  );
}

function MessageBody({ text, renderMd }: { readonly text: string; readonly renderMd: boolean }) {
  if (!text) return null;
  if (renderMd) {
    return (
      <div
        className="composer-markdown prose prose-sm max-w-none break-words text-slate-800"
        // biome-ignore lint/security/noDangerouslySetInnerHtml: renderMarkdown sanitizes via DOMPurify (src/lib/markdown.ts)
        dangerouslySetInnerHTML={{ __html: renderMarkdown(text) }}
      />
    );
  }
  return <pre className="whitespace-pre-wrap break-words font-sans text-slate-800">{text}</pre>;
}

function MessageBubble({
  role,
  target,
  targetName,
  content,
  status,
  authorUsername,
  authorDisplayName,
  recipientUsername,
  recipientDisplayName,
  currentUsername,
  showThinking,
  renderMd,
}: {
  readonly role: string;
  readonly target: string | null;
  readonly targetName: string;
  readonly content: string;
  readonly status: string;
  readonly authorUsername: string | null;
  readonly authorDisplayName: string | null;
  readonly recipientUsername: string | null;
  readonly recipientDisplayName: string | null;
  readonly currentUsername: string | null;
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

  const entityLabel = targetName.trim() || target || '';
  let speaker = t('composer.roleSystem');
  let recipient: string | null = null;
  let speakerIsYou = false;
  let recipientIsYou = false;

  if (role === 'user') {
    speaker = authorDisplayName || authorUsername || t('composer.roleUser');
    speakerIsYou = Boolean(currentUsername) && authorUsername === currentUsername;
    recipient = entityLabel || null;
  } else if (role === 'assistant') {
    speaker = entityLabel || t('composer.roleAssistant');
    recipient = recipientDisplayName || recipientUsername || t('composer.roleUser');
    recipientIsYou =
      Boolean(currentUsername) &&
      (recipientUsername === currentUsername || recipient === currentUsername);
  }

  return (
    <div className={`rounded-lg px-2 py-1.5 text-xs ${tone}`}>
      <div className="mb-0.5 flex items-center justify-between gap-2 text-[10px] text-slate-500">
        <PartyArrow
          speaker={speaker}
          recipient={recipient}
          speakerIsYou={speakerIsYou}
          recipientIsYou={recipientIsYou}
        />
        {status === 'responding' ? (
          <span className="text-amber-700">{t('composer.statusResponding')}</span>
        ) : null}
      </div>
      {thinking ? <ThinkingBlock text={thinking} /> : null}
      <MessageBody text={body || (status === 'responding' ? '…' : '')} renderMd={renderMd} />
    </div>
  );
}
