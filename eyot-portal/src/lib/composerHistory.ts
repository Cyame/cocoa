import { useCallback, useEffect, useRef, useState } from 'react';

export const COMPOSER_HISTORY_MAX = 50;

export function composerHistoryStorageKey(workspaceId: string): string {
  return `eyot-composer-history:${workspaceId}`;
}

type ReadableStorage = Pick<Storage, 'getItem'>;
type WritableStorage = Pick<Storage, 'setItem'>;

export function loadComposerHistory(
  workspaceId: string,
  storage: ReadableStorage = localStorage,
): string[] {
  try {
    const raw = storage.getItem(composerHistoryStorageKey(workspaceId));
    if (raw === null || raw === '') return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item): item is string => typeof item === 'string' && item.length > 0)
      .slice(-COMPOSER_HISTORY_MAX);
  } catch {
    return [];
  }
}

export function persistComposerHistory(
  workspaceId: string,
  entries: readonly string[],
  storage: WritableStorage = localStorage,
): void {
  try {
    storage.setItem(
      composerHistoryStorageKey(workspaceId),
      JSON.stringify(entries.slice(-COMPOSER_HISTORY_MAX)),
    );
  } catch {
    // Quota / private-mode failures must not block sending.
  }
}

export function pushComposerHistory(entries: readonly string[], command: string): string[] {
  if (command.length === 0) return [...entries];
  if (entries.at(-1) === command) return [...entries];
  const next = [...entries, command];
  return next.length > COMPOSER_HISTORY_MAX ? next.slice(-COMPOSER_HISTORY_MAX) : next;
}

export function isCursorOnFirstLine(text: string, cursor: number): boolean {
  const pos = Math.min(Math.max(0, cursor), text.length);
  return !text.slice(0, pos).includes('\n');
}

export function isCursorOnLastLine(text: string, cursor: number): boolean {
  const pos = Math.min(Math.max(0, cursor), text.length);
  return !text.slice(pos).includes('\n');
}

export type ComposerHistoryBrowse = {
  readonly entries: readonly string[];
  readonly browseIndex: number | null;
  readonly draft: string;
};

export type HistoryRecall =
  | { readonly action: 'apply'; readonly text: string; readonly session: ComposerHistoryBrowse }
  | { readonly action: 'stay' }
  | { readonly action: 'ignore' };

export function recallOlder(session: ComposerHistoryBrowse, currentText: string): HistoryRecall {
  if (session.entries.length === 0) return { action: 'ignore' };
  if (session.browseIndex === 0) return { action: 'stay' };
  const browseIndex =
    session.browseIndex === null ? session.entries.length - 1 : session.browseIndex - 1;
  const text = session.entries[browseIndex];
  if (text === undefined) return { action: 'ignore' };
  return {
    action: 'apply',
    text,
    session: {
      entries: session.entries,
      browseIndex,
      draft: session.browseIndex === null ? currentText : session.draft,
    },
  };
}

export function recallNewer(session: ComposerHistoryBrowse): HistoryRecall {
  if (session.browseIndex === null) return { action: 'ignore' };
  if (session.browseIndex >= session.entries.length - 1) {
    return {
      action: 'apply',
      text: session.draft,
      session: { ...session, browseIndex: null },
    };
  }
  const browseIndex = session.browseIndex + 1;
  const text = session.entries[browseIndex];
  if (text === undefined) return { action: 'ignore' };
  return {
    action: 'apply',
    text,
    session: { ...session, browseIndex },
  };
}

export function useComposerCommandHistory(workspaceId: string) {
  const [entries, setEntries] = useState<string[]>(() => loadComposerHistory(workspaceId));
  const browseIndexRef = useRef<number | null>(null);
  const draftRef = useRef('');
  const entriesRef = useRef(entries);
  entriesRef.current = entries;

  useEffect(() => {
    const loaded = loadComposerHistory(workspaceId);
    setEntries(loaded);
    entriesRef.current = loaded;
    browseIndexRef.current = null;
    draftRef.current = '';
  }, [workspaceId]);

  const snapshot = useCallback(
    (): ComposerHistoryBrowse => ({
      entries: entriesRef.current,
      browseIndex: browseIndexRef.current,
      draft: draftRef.current,
    }),
    [],
  );

  const applySession = useCallback((session: ComposerHistoryBrowse) => {
    browseIndexRef.current = session.browseIndex;
    draftRef.current = session.draft;
  }, []);

  const commit = useCallback(
    (command: string) => {
      const next = pushComposerHistory(entriesRef.current, command);
      entriesRef.current = next;
      setEntries(next);
      persistComposerHistory(workspaceId, next);
      browseIndexRef.current = null;
      draftRef.current = '';
    },
    [workspaceId],
  );

  const older = useCallback(
    (currentText: string): HistoryRecall => {
      const result = recallOlder(snapshot(), currentText);
      if (result.action === 'apply') applySession(result.session);
      return result;
    },
    [applySession, snapshot],
  );

  const newer = useCallback((): HistoryRecall => {
    const result = recallNewer(snapshot());
    if (result.action === 'apply') applySession(result.session);
    return result;
  }, [applySession, snapshot]);

  const isBrowsing = useCallback(() => browseIndexRef.current !== null, []);

  return { commit, older, newer, isBrowsing };
}
