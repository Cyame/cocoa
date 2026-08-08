import { AtSign } from 'lucide-react';
import { type RefObject, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';

export type MentionCandidate = {
  readonly entity_id: string;
  readonly slug: string;
  readonly name: string;
  readonly preset_slug: string | null;
  readonly instance_id: string;
  readonly membership_id: string;
  readonly instance_status?: string;
  readonly mentionable?: boolean;
};

type ActiveToken = {
  readonly start: number;
  readonly filter: string;
};

function findActiveMention(text: string, cursor: number): ActiveToken | null {
  if (cursor < 0 || cursor > text.length) return null;
  let i = cursor - 1;
  while (i >= 0) {
    const ch = text[i];
    if (ch === '@') {
      const prev = i === 0 ? '' : text[i - 1];
      // Trigger after start / whitespace / punctuation / CJK — not only ASCII space.
      if (i === 0 || !/[A-Za-z0-9_]/.test(prev)) {
        const filter = text.slice(i + 1, cursor);
        if (/^[A-Za-z0-9_-]*$/.test(filter)) {
          return { start: i, filter };
        }
      }
      return null;
    }
    if (!/[A-Za-z0-9_-]/.test(ch)) return null;
    i -= 1;
  }
  return null;
}

export type MentionAutocompleteProps = {
  readonly textareaRef: RefObject<HTMLTextAreaElement | null>;
  readonly text: string;
  readonly onTextChange: (newText: string) => void;
  readonly workspaceId: string;
  /** When command menu is open, suppress mention menu. */
  readonly suppressed?: boolean;
};

export function MentionAutocomplete({
  textareaRef,
  text,
  onTextChange,
  workspaceId,
  suppressed = false,
}: MentionAutocompleteProps) {
  const { t } = useTranslation();
  const [cursor, setCursor] = useState(0);
  const [highlighted, setHighlighted] = useState(0);
  const [dismissedStart, setDismissedStart] = useState<number | null>(null);
  const [candidates, setCandidates] = useState<readonly MentionCandidate[]>([]);
  const loadedFor = useRef<string | null>(null);

  useEffect(() => {
    if (loadedFor.current === workspaceId) return;
    loadedFor.current = workspaceId;
    let cancelled = false;
    void api<{ items: MentionCandidate[] }>(
      `/workspaces/${encodeURIComponent(workspaceId)}/mention-candidates`,
    )
      .then((res) => {
        if (!cancelled) setCandidates(res.items);
      })
      .catch(() => {
        if (!cancelled) setCandidates([]);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  // Refresh candidates periodically while typing @ (passages may change)
  useEffect(() => {
    if (!text.includes('@')) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void api<{ items: MentionCandidate[] }>(
        `/workspaces/${encodeURIComponent(workspaceId)}/mention-candidates`,
      )
        .then((res) => {
          if (!cancelled) setCandidates(res.items);
        })
        .catch(() => undefined);
    }, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [text, workspaceId]);

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

  const activeToken = useMemo(() => findActiveMention(text, cursor), [text, cursor]);

  const filtered = useMemo(() => {
    if (activeToken === null) return [];
    const f = activeToken.filter.toLowerCase();
    return candidates.filter(
      (c) => c.slug.toLowerCase().includes(f) || c.name.toLowerCase().includes(f),
    );
  }, [candidates, activeToken]);

  const visible =
    !suppressed &&
    activeToken !== null &&
    dismissedStart !== activeToken.start &&
    filtered.length > 0;

  useEffect(() => {
    setHighlighted(0);
  }, []);

  const handleSelect = useCallback(
    (slug: string) => {
      const textarea = textareaRef.current;
      if (activeToken === null) return;
      const before = text.slice(0, activeToken.start);
      const after = text.slice(cursor);
      const inserted = `@${slug} `;
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
        setHighlighted((h) => (h + 1) % filtered.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setHighlighted((h) => (h - 1 + filtered.length) % filtered.length);
      } else if (e.key === 'Enter' || e.key === 'Tab') {
        if (activeToken === null) return;
        e.preventDefault();
        const chosen = filtered[highlighted];
        if (chosen !== undefined && chosen.mentionable !== false) handleSelect(chosen.slug);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        if (activeToken !== null) setDismissedStart(activeToken.start);
      } else if (e.key === 'Backspace' && activeToken !== null && activeToken.filter.length === 0) {
        setDismissedStart(activeToken.start);
      }
    };
    textarea.addEventListener('keydown', onKeyDown);
    return () => textarea.removeEventListener('keydown', onKeyDown);
  }, [textareaRef, visible, filtered, highlighted, activeToken, handleSelect]);

  if (!visible) return null;

  return (
    <div
      role="listbox"
      aria-label={t('composer.mentionSuggestions')}
      className="absolute bottom-full left-0 right-0 z-20 mb-1 max-h-48 overflow-y-auto rounded-lg border border-slate-300 bg-white shadow-lg"
    >
      {filtered.map((item, idx) => {
        const isHighlighted = idx === highlighted;
        const canMention = item.mentionable !== false;
        const tip = canMention
          ? undefined
          : t('composer.mentionInactive', {
              status: item.instance_status ?? 'stopped',
            });
        return (
          <button
            key={item.entity_id}
            type="button"
            role="option"
            aria-selected={isHighlighted}
            aria-disabled={!canMention}
            disabled={!canMention}
            title={tip}
            onMouseDown={(e) => {
              e.preventDefault();
              if (!canMention) return;
              handleSelect(item.slug);
            }}
            className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm ${
              !canMention
                ? 'cursor-not-allowed bg-slate-50 text-slate-400'
                : isHighlighted
                  ? 'bg-blue-100'
                  : 'bg-white hover:bg-slate-50'
            }`}
          >
            <AtSign className="h-4 w-4 flex-shrink-0 text-slate-500" />
            <code className="font-mono">@{item.slug}</code>
            <span className="truncate">{item.name}</span>
            {!canMention ? (
              <span className="ml-auto shrink-0 text-[10px] uppercase tracking-wide">
                {item.instance_status ?? 'inactive'}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
