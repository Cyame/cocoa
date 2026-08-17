import { describe, expect, it } from 'vitest';
import { type ActivityItem, ingestActivityFrame, isSubagentTool } from '@/lib/composerTranscript';

describe('ingestActivityFrame', () => {
  it('creates a thinking activity on start', () => {
    const result = ingestActivityFrame([], {
      kind: 'thinking',
      status: 'start',
    });
    expect(result).toHaveLength(1);
    expect(result[0]?.kind).toBe('thinking');
    expect(result[0]?.status).toBe('start');
    expect(result[0]?.deltas).toBe('');
  });

  it('accumulates thinking deltas', () => {
    let items: ActivityItem[] = [];
    items = ingestActivityFrame(items, { kind: 'thinking', status: 'start' });
    items = ingestActivityFrame(items, { kind: 'thinking', status: 'delta', delta: 'hello ' });
    items = ingestActivityFrame(items, { kind: 'thinking', status: 'delta', delta: 'world' });
    expect(items).toHaveLength(1);
    expect(items[0]?.deltas).toBe('hello world');
  });

  it('ends thinking activity', () => {
    let items: ActivityItem[] = [];
    items = ingestActivityFrame(items, { kind: 'thinking', status: 'start' });
    items = ingestActivityFrame(items, { kind: 'thinking', status: 'delta', delta: 'content' });
    items = ingestActivityFrame(items, { kind: 'thinking', status: 'end' });
    expect(items).toHaveLength(1);
    expect(items[0]?.status).toBe('end');
    expect(items[0]?.deltas).toBe('content');
  });

  it('creates a tool_use card on start', () => {
    const result = ingestActivityFrame([], {
      kind: 'tool_use',
      status: 'start',
      tool_name: 'write_file',
    });
    expect(result).toHaveLength(1);
    expect(result[0]?.kind).toBe('tool_use');
    expect(result[0]?.toolName).toBe('write_file');
    expect(result[0]?.status).toBe('start');
  });

  it('accumulates tool_use deltas', () => {
    let items: ActivityItem[] = [];
    items = ingestActivityFrame(items, {
      kind: 'tool_use',
      status: 'start',
      tool_name: 'write_file',
    });
    items = ingestActivityFrame(items, {
      kind: 'tool_use',
      status: 'delta',
      tool_name: 'write_file',
      delta: '{"path":',
    });
    items = ingestActivityFrame(items, {
      kind: 'tool_use',
      status: 'delta',
      tool_name: 'write_file',
      delta: ' "/tmp"}',
    });
    expect(items).toHaveLength(1);
    expect(items[0]?.deltas).toBe('{"path": "/tmp"}');
  });

  it('ends tool_use card', () => {
    let items: ActivityItem[] = [];
    items = ingestActivityFrame(items, {
      kind: 'tool_use',
      status: 'start',
      tool_name: 'write_file',
    });
    items = ingestActivityFrame(items, {
      kind: 'tool_use',
      status: 'end',
      tool_name: 'write_file',
    });
    expect(items).toHaveLength(1);
    expect(items[0]?.status).toBe('end');
  });

  it('deduplicates toolcall and tool_execution for same tool_name', () => {
    let items: ActivityItem[] = [];
    items = ingestActivityFrame(items, {
      kind: 'tool_use',
      status: 'start',
      tool_name: 'write_file',
    });
    items = ingestActivityFrame(items, {
      kind: 'tool_use',
      status: 'start',
      tool_name: 'write_file',
    });
    expect(items).toHaveLength(1);
  });

  it('keeps separate cards for different tool_names', () => {
    let items: ActivityItem[] = [];
    items = ingestActivityFrame(items, {
      kind: 'tool_use',
      status: 'start',
      tool_name: 'tool_a',
    });
    items = ingestActivityFrame(items, {
      kind: 'tool_use',
      status: 'start',
      tool_name: 'tool_b',
    });
    expect(items).toHaveLength(2);
  });

  it('handles interleaved thinking and tool_use', () => {
    let items: ActivityItem[] = [];
    items = ingestActivityFrame(items, { kind: 'thinking', status: 'start' });
    items = ingestActivityFrame(items, {
      kind: 'tool_use',
      status: 'start',
      tool_name: 'tool_a',
    });
    items = ingestActivityFrame(items, { kind: 'thinking', status: 'delta', delta: 'hmm' });
    items = ingestActivityFrame(items, {
      kind: 'tool_use',
      status: 'end',
      tool_name: 'tool_a',
    });
    expect(items).toHaveLength(2);
    expect(items[0]?.kind).toBe('thinking');
    expect(items[0]?.deltas).toBe('hmm');
    expect(items[1]?.kind).toBe('tool_use');
    expect(items[1]?.status).toBe('end');
  });

  it('does not append delta when no matching open activity exists', () => {
    const items: ActivityItem[] = [];
    const result = ingestActivityFrame(items, {
      kind: 'tool_use',
      status: 'delta',
      tool_name: 'orphan_tool',
      delta: 'data',
    });
    expect(result).toHaveLength(0);
  });
});

describe('isSubagentTool', () => {
  it('matches subagent patterns', () => {
    expect(isSubagentTool('subagent-ops')).toBe(true);
    expect(isSubagentTool('research-subagent')).toBe(true);
    expect(isSubagentTool('SubAgent-Main')).toBe(true);
  });

  it('does not match non-subagent tools', () => {
    expect(isSubagentTool('write_file')).toBe(false);
    expect(isSubagentTool('read_file')).toBe(false);
    expect(isSubagentTool('bash')).toBe(false);
  });
});
