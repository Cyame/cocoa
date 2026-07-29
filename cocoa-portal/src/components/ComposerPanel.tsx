import { AlertCircle, LoaderCircle, MessageSquare, Send } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CommandAutocomplete } from '@/components/CommandAutocomplete';
import { ApiError, api } from '@/lib/api';
import {
  type Compartment,
  parse_turn,
  SlashParserError,
  segmentCompartments,
  type Turn,
} from '@/lib/slash-parser';
import type { EmployeePreset } from '@/lib/types';

type MessageSendResult = {
  readonly directives: readonly string[];
  readonly general_text: string | null;
  readonly results: readonly unknown[];
};

type PresetCache = Record<string, EmployeePreset | null>;

type ComposerPanelProps = {
  readonly workspaceId: string;
  readonly compact?: boolean;
};

export default function ComposerPanel({ workspaceId, compact = false }: ComposerPanelProps) {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  const [parseError, setParseError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState<MessageSendResult | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [_presetCache, setPresetCache] = useState<PresetCache>({});
  const fetchedSlugsRef = useRef<Set<string>>(new Set());
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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

  useEffect(() => {
    let isActive = true;
    const toFetch = targetSlugs.filter((s) => !fetchedSlugsRef.current.has(s));
    if (toFetch.length === 0) return;

    for (const s of toFetch) {
      fetchedSlugsRef.current.add(s);
    }

    void Promise.all(
      toFetch.map(async (slug): Promise<[string, EmployeePreset | null]> => {
        try {
          const preset = await api<EmployeePreset>(`/base-classes/${encodeURIComponent(slug)}`);
          return [slug, preset as unknown as EmployeePreset];
        } catch {
          return [slug, null];
        }
      }),
    ).then((results) => {
      if (!isActive) return;
      setPresetCache((prev) => {
        const next: PresetCache = { ...prev };
        for (const [slug, preset] of results) {
          next[slug] = preset;
        }
        return next;
      });
    });

    return () => {
      isActive = false;
    };
  }, [targetSlugs]);

  const canSend = text.trim().length > 0 && parseError === null && !sending;

  async function handleSend() {
    if (!canSend) return;
    setSending(true);
    setSendError(null);
    setSendResult(null);
    try {
      const result = await api<MessageSendResult>('/messaging/messages', {
        method: 'POST',
        body: JSON.stringify({ turn_text: text, workspace_id: workspaceId }),
      });
      setSendResult(result);
    } catch (e) {
      setSendError(e instanceof ApiError ? e.message : t('composer.sendFailed'));
    } finally {
      setSending(false);
    }
  }

  const textareaHeight = compact ? 'h-48' : 'h-80';

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

      {sendResult !== null ? (
        <div className="mb-3 rounded-lg border border-green-300 bg-green-50 px-3 py-2 text-xs text-green-800">
          {t('composer.sentDirectives', { count: sendResult.directives.length })}
        </div>
      ) : null}

      <div className="relative min-h-0 flex-1">
        <textarea
          ref={textareaRef}
          id="composer-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t('composer.placeholder')}
          className={`${textareaHeight} w-full rounded-lg border border-slate-300 p-3 font-mono text-sm text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500`}
          spellCheck={false}
        />
        <CommandAutocomplete
          textareaRef={textareaRef}
          text={text}
          onTextChange={setText}
          targetSlugs={targetSlugs}
        />
      </div>

      {compartments.length > 0 ? (
        <ul className="mt-2 max-h-24 overflow-y-auto text-xs text-slate-600">
          {compartments.map((c) => (
            <li key={c.label} className="truncate font-mono">
              {c.label}: {c.directives.length} directive(s)
            </li>
          ))}
        </ul>
      ) : null}

      <div className="mt-3 flex items-center justify-end">
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
          {t('composer.send')}
        </button>
      </div>
    </section>
  );
}
