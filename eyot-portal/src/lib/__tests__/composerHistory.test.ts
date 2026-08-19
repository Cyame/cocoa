import { describe, expect, it } from 'vitest';
import {
  COMPOSER_HISTORY_MAX,
  composerHistoryStorageKey,
  isCursorOnFirstLine,
  isCursorOnLastLine,
  loadComposerHistory,
  persistComposerHistory,
  pushComposerHistory,
  recallNewer,
  recallOlder,
  type ComposerHistoryBrowse,
} from '@/lib/composerHistory';

function memoryStorage(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    getItem: (key: string) => (key in data ? data[key] : null),
    setItem: (key: string, value: string) => {
      data[key] = value;
    },
    data,
  };
}

function session(
  entries: readonly string[],
  browseIndex: number | null = null,
  draft = '',
): ComposerHistoryBrowse {
  return { entries, browseIndex, draft };
}

describe('pushComposerHistory', () => {
  it('ignores empty commands', () => {
    expect(pushComposerHistory(['@fox hi'], '')).toEqual(['@fox hi']);
  });

  it('does not duplicate the last command', () => {
    expect(pushComposerHistory(['a', 'b'], 'b')).toEqual(['a', 'b']);
  });

  it('allows a command that appeared earlier but is not last', () => {
    expect(pushComposerHistory(['a', 'b'], 'a')).toEqual(['a', 'b', 'a']);
  });

  it('caps at COMPOSER_HISTORY_MAX', () => {
    const filled = Array.from({ length: COMPOSER_HISTORY_MAX }, (_, i) => `cmd-${i}`);
    const next = pushComposerHistory(filled, 'newest');
    expect(next).toHaveLength(COMPOSER_HISTORY_MAX);
    expect(next[0]).toBe('cmd-1');
    expect(next.at(-1)).toBe('newest');
  });
});

describe('load/persistComposerHistory', () => {
  it('round-trips entries per workspace', () => {
    const storage = memoryStorage();
    persistComposerHistory('ws-1', ['@fox /status', '@lion hi'], storage);
    expect(loadComposerHistory('ws-1', storage)).toEqual(['@fox /status', '@lion hi']);
    expect(loadComposerHistory('ws-2', storage)).toEqual([]);
  });

  it('returns empty on corrupt JSON', () => {
    const key = composerHistoryStorageKey('ws-1');
    const storage = memoryStorage({ [key]: '{not-json' });
    expect(loadComposerHistory('ws-1', storage)).toEqual([]);
  });

  it('drops non-string entries', () => {
    const key = composerHistoryStorageKey('ws-1');
    const storage = memoryStorage({ [key]: JSON.stringify(['ok', 12, null, '']) });
    expect(loadComposerHistory('ws-1', storage)).toEqual(['ok']);
  });
});

describe('cursor line helpers', () => {
  it('treats a single line as both first and last', () => {
    expect(isCursorOnFirstLine('hello', 3)).toBe(true);
    expect(isCursorOnLastLine('hello', 3)).toBe(true);
  });

  it('detects first vs last line in multiline text', () => {
    const text = 'one\ntwo\nthree';
    expect(isCursorOnFirstLine(text, 2)).toBe(true);
    expect(isCursorOnLastLine(text, 2)).toBe(false);
    expect(isCursorOnFirstLine(text, 5)).toBe(false);
    expect(isCursorOnLastLine(text, text.length)).toBe(true);
  });
});

describe('recallOlder / recallNewer', () => {
  it('ignores older when history is empty', () => {
    expect(recallOlder(session([]), 'draft').action).toBe('ignore');
  });

  it('walks from live draft to oldest then stays', () => {
    const live = session(['first', 'second', 'third'], null, '');
    const toThird = recallOlder(live, 'unsent');
    expect(toThird).toMatchObject({ action: 'apply', text: 'third' });
    if (toThird.action !== 'apply') return;
    expect(toThird.session.draft).toBe('unsent');

    const toSecond = recallOlder(toThird.session, 'unsent');
    expect(toSecond).toMatchObject({ action: 'apply', text: 'second' });
    if (toSecond.action !== 'apply') return;

    const toFirst = recallOlder(toSecond.session, 'unsent');
    expect(toFirst).toMatchObject({ action: 'apply', text: 'first' });
    if (toFirst.action !== 'apply') return;

    expect(recallOlder(toFirst.session, 'unsent').action).toBe('stay');
  });

  it('restores the stashed draft after stepping newer past the latest', () => {
    const browsing = session(['a', 'b'], 1, 'live-draft');
    const restored = recallNewer(browsing);
    expect(restored).toMatchObject({ action: 'apply', text: 'live-draft' });
    if (restored.action !== 'apply') return;
    expect(restored.session.browseIndex).toBeNull();
    expect(recallNewer(restored.session).action).toBe('ignore');
  });

  it('steps newer toward the latest command', () => {
    const browsing = session(['a', 'b', 'c'], 0, 'draft');
    const next = recallNewer(browsing);
    expect(next).toMatchObject({ action: 'apply', text: 'b' });
  });
});
