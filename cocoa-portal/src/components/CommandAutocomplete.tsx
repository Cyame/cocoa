import { Terminal } from 'lucide-react';
import { type RefObject, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';
import type { EmployeePreset } from '@/lib/types';

export const GLOBAL_COMMANDS = ['/read', '/list', '/write', '/archive'] as const;
export const CONTROL_COMMANDS = [
  '/interrupt',
  '/pause',
  '/resume',
  '/status',
  '/snapshot',
] as const;
export const LEARNING_COMMANDS = ['/distill', '/consolidate', '/reflect'] as const;

type CommandGroup = {
  readonly label: string;
  readonly commands: readonly string[];
};

type ActiveToken = {
  readonly start: number;
  readonly filter: string;
};

function findActiveToken(text: string, cursor: number): ActiveToken | null {
  if (cursor < 0 || cursor > text.length) return null;
  let i = cursor - 1;
  while (i >= 0) {
    const ch = text[i];
    if (ch === '/') {
      const prev = i === 0 ? '' : text[i - 1];
      // Allow after whitespace OR any non-word char (Chinese, punctuation).
      if (i === 0 || !/[A-Za-z0-9_]/.test(prev)) {
        const filter = text.slice(i + 1, cursor);
        if (/^[A-Za-z-]*$/.test(filter)) {
          return { start: i, filter };
        }
      }
      return null;
    }
    if (!/[A-Za-z-]/.test(ch)) return null;
    i -= 1;
  }
  return null;
}

export type CommandAutocompleteProps = {
  readonly textareaRef: RefObject<HTMLTextAreaElement | null>;
  readonly text: string;
  readonly onTextChange: (newText: string) => void;
  readonly targetSlugs: readonly string[];
  /** entity slug → base-class / preset slug for per-preset commands */
  readonly presetByEntitySlug?: Readonly<Record<string, string | null | undefined>>;
  readonly onOpenChange?: (open: boolean) => void;
};

export function CommandAutocomplete({
  textareaRef,
  text,
  onTextChange,
  targetSlugs,
  presetByEntitySlug = {},
  onOpenChange,
}: CommandAutocompleteProps) {
  const { t } = useTranslation();
  const [cursor, setCursor] = useState(0);
  const [highlighted, setHighlighted] = useState(0);
  const [dismissedStart, setDismissedStart] = useState<number | null>(null);
  const [presetCommands, setPresetCommands] = useState<Readonly<Record<string, readonly string[]>>>(
    {},
  );
  const cacheRef = useRef<Map<string, readonly string[]>>(new Map());

  useEffect(() => {
    const lookupKeys = [
      ...new Set(
        targetSlugs
          .map((s) => presetByEntitySlug[s])
          .filter((s): s is string => typeof s === 'string' && s.length > 0),
      ),
    ];
    const missing = lookupKeys.filter((s) => !cacheRef.current.has(s));
    if (missing.length === 0) return;
    let cancelled = false;
    void Promise.all(
      missing.map(async (slug) => {
        try {
          const preset = await api<EmployeePreset>(`/base-classes/${encodeURIComponent(slug)}`);
          const cmds = preset.manifest?.commands ?? [];
          cacheRef.current.set(slug, cmds);
        } catch {
          cacheRef.current.set(slug, []);
        }
      }),
    ).then(() => {
      if (!cancelled) {
        setPresetCommands(Object.fromEntries(cacheRef.current.entries()));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [targetSlugs, presetByEntitySlug]);

  const groups = useMemo<readonly CommandGroup[]>(() => {
    const base: CommandGroup[] = [
      { label: t('topology.commandGroupGlobal'), commands: GLOBAL_COMMANDS },
      { label: t('topology.commandGroupControl'), commands: CONTROL_COMMANDS },
      { label: t('topology.commandGroupLearning'), commands: LEARNING_COMMANDS },
    ];
    if (targetSlugs.length === 0) return base;
    const perPreset: CommandGroup[] = [];
    for (const slug of targetSlugs) {
      const presetKey = presetByEntitySlug[slug] || slug;
      const cmds = presetCommands[presetKey];
      if (cmds !== undefined && cmds.length > 0) {
        perPreset.push({ label: slug, commands: cmds });
      }
    }
    return [...base, ...perPreset];
  }, [targetSlugs, presetCommands, presetByEntitySlug, t]);

  const activeToken = useMemo(() => findActiveToken(text, cursor), [text, cursor]);

  const groupedFlat = useMemo(() => {
    if (activeToken === null) return [];
    const filter = `/${activeToken.filter}`;
    let idx = 0;
    const result: { label: string; items: { cmd: string; idx: number }[] }[] = [];
    for (const g of groups) {
      const items: { cmd: string; idx: number }[] = [];
      for (const c of g.commands) {
        if (c.startsWith(filter)) {
          items.push({ cmd: c, idx });
          idx += 1;
        }
      }
      if (items.length > 0) {
        result.push({ label: g.label, items });
      }
    }
    return result;
  }, [groups, activeToken]);

  const flatCommands = useMemo<readonly string[]>(
    () => groupedFlat.flatMap((g) => g.items.map((i) => i.cmd)),
    [groupedFlat],
  );

  const visible =
    activeToken !== null && dismissedStart !== activeToken.start && flatCommands.length > 0;

  useEffect(() => {
    onOpenChange?.(visible);
  }, [visible, onOpenChange]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea === null) return;
    const update = () => setCursor(textarea.selectionStart);
    update();
    textarea.addEventListener('click', update);
    textarea.addEventListener('keyup', update);
    textarea.addEventListener('select', update);
    textarea.addEventListener('input', update);
    return () => {
      textarea.removeEventListener('click', update);
      textarea.removeEventListener('keyup', update);
      textarea.removeEventListener('select', update);
      textarea.removeEventListener('input', update);
    };
  }, [textareaRef]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea === null) {
      setCursor(text.length);
      return;
    }
    setCursor(textarea.selectionStart);
  }, [text, textareaRef]);

  const activeFilter = activeToken?.filter ?? null;
  useEffect(() => {
    setHighlighted(0);
  }, [activeFilter]);

  const handleSelect = useCallback(
    (cmd: string) => {
      const textarea = textareaRef.current;
      if (activeToken === null) return;
      const before = text.slice(0, activeToken.start);
      const after = text.slice(cursor);
      const inserted = `${cmd} `;
      const newText = before + inserted + after;
      const newCursor = before.length + inserted.length;
      setDismissedStart(activeToken.start);
      onTextChange(newText);
      if (textarea !== null) {
        requestAnimationFrame(() => {
          textarea.focus();
          textarea.setSelectionRange(newCursor, newCursor);
        });
      }
    },
    [textareaRef, text, cursor, activeToken, onTextChange],
  );

  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea === null || !visible) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setHighlighted((h) => (h + 1) % flatCommands.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setHighlighted((h) => (h - 1 + flatCommands.length) % flatCommands.length);
      } else if (e.key === 'Enter' || e.key === 'Tab') {
        // Only auto-complete when the user has typed a filter; bare "/" must stay
        // editable (Backspace / continue typing) without forcing a pick.
        if (activeToken === null || activeToken.filter.length === 0) return;
        e.preventDefault();
        const chosen = flatCommands[highlighted];
        if (chosen !== undefined) handleSelect(chosen);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        if (activeToken !== null) setDismissedStart(activeToken.start);
      } else if (e.key === 'Backspace' && activeToken !== null && activeToken.filter.length === 0) {
        // Deleting the bare "/" — dismiss menu; let the default delete happen.
        setDismissedStart(activeToken.start);
      }
    };
    textarea.addEventListener('keydown', onKeyDown);
    return () => textarea.removeEventListener('keydown', onKeyDown);
  }, [textareaRef, visible, flatCommands, highlighted, activeToken, handleSelect]);

  if (!visible) return null;

  return (
    <div
      role="listbox"
      aria-label="Command suggestions"
      className="absolute bottom-full left-0 right-0 z-20 mb-1 max-h-48 overflow-y-auto rounded-lg border border-slate-300 bg-white shadow-lg"
    >
      {groupedFlat.map((group) => (
        <div key={group.label}>
          <div className="px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            {group.label}
          </div>
          {group.items.map((item) => {
            const isHighlighted = item.idx === highlighted;
            return (
              <button
                key={`${group.label}-${item.cmd}`}
                type="button"
                role="option"
                aria-selected={isHighlighted}
                onMouseDown={(e) => {
                  e.preventDefault();
                  handleSelect(item.cmd);
                }}
                className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm ${
                  isHighlighted ? 'bg-blue-100' : 'bg-white hover:bg-slate-50'
                }`}
              >
                <Terminal className="h-4 w-4 flex-shrink-0 text-slate-500" />
                <code className="font-mono text-slate-900">{item.cmd}</code>
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}
