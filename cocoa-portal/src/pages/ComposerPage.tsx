import { AlertCircle, AtSign, LoaderCircle, MessageSquare, Send } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router';
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
import { useSelectedStore } from '@/stores/selected';

type MessageSendResult = {
  readonly directives: readonly string[];
  readonly general_text: string | null;
  readonly results: readonly unknown[];
};

type PresetCache = Record<string, EmployeePreset | null>;

export default function ComposerPage() {
  const { id: officeId } = useParams<{ id: string }>();
  const setOfficeId = useSelectedStore((state) => state.setOfficeId);
  const [text, setText] = useState('');
  const [parseError, setParseError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState<MessageSendResult | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [presetCache, setPresetCache] = useState<PresetCache>({});
  const fetchedSlugsRef = useRef<Set<string>>(new Set());
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (officeId !== undefined) {
      setOfficeId(officeId);
    }
    return () => setOfficeId(null);
  }, [officeId, setOfficeId]);

  // Parse the text in real-time. The parser is pure and only throws for
  // non-string input (defensive guard), but we surface any error as a banner.
  const { turn, error } = useMemo<{ turn: Turn | null; error: string | null }>(() => {
    try {
      return { turn: parse_turn(text), error: null };
    } catch (e) {
      const msg = e instanceof SlashParserError ? e.message : 'Parse error';
      return { turn: null, error: msg };
    }
  }, [text]);

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
      if (d.target_employee !== null && !seen.has(d.target_employee)) {
        seen.add(d.target_employee);
        result.push(d.target_employee);
      }
    }
    return result;
  }, [turn]);

  // Fetch preset manifests for each targeted slug (for command hints).
  // Guarded by a ref so we never re-fetch a slug already fetched.
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
          const preset = await api<EmployeePreset>(`/employee-presets/${encodeURIComponent(slug)}`);
          return [slug, preset];
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
    if (officeId === undefined || !canSend) return;
    setSending(true);
    setSendError(null);
    setSendResult(null);
    try {
      const result = await api<MessageSendResult>('/messaging/messages', {
        method: 'POST',
        body: JSON.stringify({ turn_text: text, office_id: officeId }),
      });
      setSendResult(result);
    } catch (e) {
      setSendError(e instanceof ApiError ? e.message : 'Send failed');
    } finally {
      setSending(false);
    }
  }

  const directiveCount = turn?.directives.length ?? 0;
  const hasGeneralText = turn?.general_text !== null;

  return (
    <section className="mx-auto w-full max-w-6xl p-6 lg:p-8">
      <header className="mb-6 flex items-center gap-3">
        <MessageSquare className="h-6 w-6 text-slate-700" />
        <h1 className="text-2xl font-semibold text-slate-900">Composer</h1>
      </header>

      {parseError !== null && (
        <div
          role="alert"
          className="mb-4 flex items-center gap-2 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          <AlertCircle className="h-5 w-5 flex-shrink-0" />
          <span>Parse error: {parseError}</span>
        </div>
      )}

      {sendError !== null && (
        <div
          role="alert"
          className="mb-4 flex items-center gap-2 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          <AlertCircle className="h-5 w-5 flex-shrink-0" />
          <span>Send failed: {sendError}</span>
        </div>
      )}

      {sendResult !== null && (
        <div className="mb-4 rounded-lg border border-green-300 bg-green-50 px-4 py-3 text-sm text-green-800">
          Sent {sendResult.directives.length} directive(s).
          {sendResult.general_text !== null ? ' General text delivered.' : ''}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div>
          <label htmlFor="composer-text" className="mb-2 block text-sm font-medium text-slate-700">
            Turn text
          </label>
          <div className="relative">
            <textarea
              ref={textareaRef}
              id="composer-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Type your turn... use @slug /command to address an employee, @workspace:path to attach content."
              className="h-80 w-full rounded-lg border border-slate-300 p-4 font-mono text-sm text-slate-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              spellCheck={false}
            />
            <CommandAutocomplete
              textareaRef={textareaRef}
              text={text}
              onTextChange={setText}
              targetSlugs={targetSlugs}
            />
          </div>
          <div className="mt-3 flex items-center justify-between">
            <p className="text-xs text-slate-500">
              {directiveCount} directive(s){hasGeneralText ? ' + general text' : ''}
            </p>
            <button
              type="button"
              onClick={handleSend}
              disabled={!canSend}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {sending ? (
                <LoaderCircle className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              {sending ? 'Sending...' : 'Send'}
            </button>
          </div>
        </div>

        <div>
          <h2 className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
            <AtSign className="h-4 w-4" />
            Compartments
          </h2>
          <div className="space-y-3">
            {compartments.map((comp) => (
              <CompartmentCard
                key={comp.label}
                compartment={comp}
                preset={presetCache[comp.label] ?? undefined}
              />
            ))}
            {compartments.length === 0 && (
              <p className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-8 text-center text-sm text-slate-400">
                Start typing to see compartment preview.
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

type CompartmentCardProps = {
  readonly compartment: Compartment;
  readonly preset?: EmployeePreset;
};

function CompartmentCard({ compartment, preset }: CompartmentCardProps) {
  const isGeneral = compartment.label === 'general';
  const hasContent = compartment.general_text !== null || compartment.directives.length > 0;

  return (
    <div
      className={`rounded-lg border bg-white p-4 shadow-sm ${
        isGeneral
          ? 'border-slate-300 border-l-4 border-l-slate-400'
          : 'border-blue-200 border-l-4 border-l-blue-500'
      }`}
    >
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-800">
          {isGeneral ? 'General' : `@${compartment.label}`}
        </span>
        <span className="text-xs text-slate-400">{compartment.directives.length} cmd(s)</span>
      </div>

      {compartment.general_text !== null && (
        <p className="mb-2 truncate text-sm text-slate-600">{compartment.general_text}</p>
      )}

      {compartment.directives.map((d) => (
        <div
          key={d.raw_text}
          className="mb-2 rounded border border-slate-100 bg-slate-50 px-3 py-2 text-xs"
        >
          <div className="flex items-center gap-2">
            <code className="font-mono text-blue-600">{d.cmd}</code>
            {d.args.length > 0 && <span className="text-slate-500">{d.args.join(' ')}</span>}
          </div>
          {d.content_ref !== null && (
            <p className="mt-1 text-slate-500">
              ref: @{d.content_ref.scope}
              {d.content_ref.path !== null ? `:${d.content_ref.path}` : ''}
            </p>
          )}
        </div>
      ))}

      {preset !== undefined && preset.manifest.commands.length > 0 && (
        <div className="mt-2 border-t border-slate-100 pt-2">
          <p className="mb-1 text-xs font-medium text-slate-500">Available commands:</p>
          <div className="flex flex-wrap gap-1">
            {preset.manifest.commands.map((cmd) => (
              <span key={cmd} className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                {cmd}
              </span>
            ))}
          </div>
        </div>
      )}

      {!hasContent && <p className="text-xs text-slate-400">No content yet.</p>}
    </div>
  );
}
