import { AtSign } from 'lucide-react';
import { type RefObject, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '@/lib/api';
import { listInstances } from '@/lib/api/instances';
import type { Entity } from '@/lib/types';

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

type MergedCandidate = {
  readonly entity_id: string;
  readonly slug: string;
  readonly name: string;
  readonly preset_slug: string | null;
  readonly instance_id: string | null;
  readonly membership_id: string | null;
  readonly instance_status?: string;
  readonly introduced: boolean;
  readonly running: boolean;
};

export type IntroduceTarget = {
  readonly entity_id: string;
  readonly slug: string;
  readonly name: string;
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
  readonly suppressed?: boolean;
  readonly onIntroduceRequest?: (entity: IntroduceTarget) => void;
  readonly refreshKey?: number;
};

export function MentionAutocomplete({
  textareaRef,
  text,
  onTextChange,
  workspaceId,
  suppressed = false,
  onIntroduceRequest,
  refreshKey = 0,
}: MentionAutocompleteProps) {
  const { t } = useTranslation();
  const [cursor, setCursor] = useState(0);
  const [highlighted, setHighlighted] = useState(0);
  const [dismissedStart, setDismissedStart] = useState<number | null>(null);
  const [candidates, setCandidates] = useState<readonly MentionCandidate[]>([]);
  const [allEntities, setAllEntities] = useState<readonly Entity[]>([]);
  const [introducedEntityIds, setIntroducedEntityIds] = useState<ReadonlySet<string>>(new Set());

  // biome-ignore lint/correctness/useExhaustiveDependencies: refreshKey is a prop that triggers refetch when incremented by parent
  useEffect(() => {
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
  }, [workspaceId, refreshKey]);

  useEffect(() => {
    let cancelled = false;
    void api<{ items: Entity[] }>('/entities?limit=200&is_cerebellum=false')
      .then((res) => {
        if (!cancelled) setAllEntities(res.items);
      })
      .catch(() => {
        if (!cancelled) setAllEntities([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // biome-ignore lint/correctness/useExhaustiveDependencies: refreshKey is a prop that triggers refetch when incremented by parent
  useEffect(() => {
    let cancelled = false;
    void listInstances({ workspace_id: workspaceId, limit: 200 })
      .then((page) => {
        if (cancelled) return;
        setIntroducedEntityIds(new Set(page.items.map((i) => i.entity_id)));
      })
      .catch(() => {
        if (!cancelled) setIntroducedEntityIds(new Set());
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, refreshKey]);

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

  const merged = useMemo(() => {
    const candidateMap = new Map<string, MentionCandidate>();
    for (const c of candidates) {
      candidateMap.set(c.entity_id, c);
    }
    const result: MergedCandidate[] = [];
    const seen = new Set<string>();
    for (const c of candidates) {
      seen.add(c.entity_id);
      result.push({
        entity_id: c.entity_id,
        slug: c.slug,
        name: c.name,
        preset_slug: c.preset_slug,
        instance_id: c.instance_id,
        membership_id: c.membership_id,
        instance_status: c.instance_status,
        introduced: true,
        running: c.mentionable !== false,
      });
    }
    for (const e of allEntities) {
      if (seen.has(e.id)) continue;
      seen.add(e.id);
      const introduced = introducedEntityIds.has(e.id);
      result.push({
        entity_id: e.id,
        slug: e.slug,
        name: e.display_name ?? e.name,
        preset_slug: e.preset_slug,
        instance_id: null,
        membership_id: null,
        introduced,
        running: false,
      });
    }
    return result;
  }, [candidates, allEntities, introducedEntityIds]);

  const filtered = useMemo(() => {
    if (activeToken === null) return [];
    const f = activeToken.filter.toLowerCase();
    return merged.filter(
      (c) => c.slug.toLowerCase().includes(f) || c.name.toLowerCase().includes(f),
    );
  }, [merged, activeToken]);

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

  const triggerIntroduce = useCallback(
    (item: MergedCandidate) => {
      if (!onIntroduceRequest) return;
      if (activeToken !== null) setDismissedStart(activeToken.start);
      onIntroduceRequest({
        entity_id: item.entity_id,
        slug: item.slug,
        name: item.name,
      });
    },
    [onIntroduceRequest, activeToken],
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
        if (chosen === undefined) return;
        if (chosen.running) {
          handleSelect(chosen.slug);
        } else if (!chosen.introduced) {
          triggerIntroduce(chosen);
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        if (activeToken !== null) setDismissedStart(activeToken.start);
      } else if (e.key === 'Backspace' && activeToken !== null && activeToken.filter.length === 0) {
        setDismissedStart(activeToken.start);
      }
    };
    textarea.addEventListener('keydown', onKeyDown);
    return () => textarea.removeEventListener('keydown', onKeyDown);
  }, [textareaRef, visible, filtered, highlighted, activeToken, handleSelect, triggerIntroduce]);

  if (!visible) return null;

  return (
    <div
      role="listbox"
      aria-label={t('composer.mentionSuggestions')}
      className="absolute bottom-full left-0 right-0 z-20 mb-1 max-h-48 overflow-y-auto rounded-lg border border-slate-300 bg-white shadow-lg"
    >
      {filtered.map((item, idx) => {
        const isHighlighted = idx === highlighted;
        const stopped = item.introduced && !item.running;
        const unIntroduced = !item.introduced;
        const grayed = stopped || unIntroduced;
        const tip = stopped
          ? t('composer.mentionInactive', {
              status: item.instance_status ?? 'stopped',
            })
          : unIntroduced
            ? t('composer.mentionNotIntroduced')
            : undefined;
        return (
          <button
            key={item.entity_id}
            type="button"
            role="option"
            aria-selected={isHighlighted}
            aria-disabled={stopped}
            disabled={stopped}
            title={tip}
            onMouseDown={(e) => {
              e.preventDefault();
              if (stopped) return;
              if (item.running) {
                handleSelect(item.slug);
              } else if (unIntroduced) {
                triggerIntroduce(item);
              }
            }}
            className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm ${
              grayed
                ? unIntroduced
                  ? 'cursor-pointer bg-slate-50 text-slate-400 hover:bg-slate-100'
                  : 'cursor-not-allowed bg-slate-50 text-slate-400'
                : isHighlighted
                  ? 'bg-blue-100'
                  : 'bg-white hover:bg-slate-50'
            }`}
          >
            <AtSign className="h-4 w-4 flex-shrink-0 text-slate-500" />
            <code className="font-mono">@{item.slug}</code>
            <span className="truncate">{item.name}</span>
            {stopped ? (
              <span className="ml-auto shrink-0 text-[10px] uppercase tracking-wide">
                {item.instance_status ?? 'inactive'}
              </span>
            ) : null}
            {unIntroduced ? (
              <span className="ml-auto shrink-0 text-[10px] uppercase tracking-wide text-amber-500">
                {t('composer.mentionNotIntroducedBadge')}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
