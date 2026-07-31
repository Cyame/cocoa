import { describe, expect, it } from 'vitest';
import {
  buildOptimisticUserBubbles,
  reconcileTranscript,
  upsertAssistantBubble,
} from '@/lib/composerTranscript';

describe('composerTranscript', () => {
  it('keeps optimistic user bubbles when server returns empty', () => {
    const local = buildOptimisticUserBubbles([
      { turnId: 't1', target: 'alice', content: '@alice hi' },
    ]);
    const merged = reconcileTranscript([], local);
    expect(merged).toHaveLength(1);
    expect(merged[0]?.role).toBe('user');
    expect(merged[0]?.content).toBe('@alice hi');
  });

  it('prefers non-empty local assistant over empty server row', () => {
    const local = upsertAssistantBubble([], {
      turnId: 't1',
      target: 'alice',
      status: 'completed',
      text: 'hello from model',
      thinking: '',
    });
    const server = [
      {
        id: 'srv-1',
        role: 'assistant',
        content: '',
        target_entity: 'alice',
        turn_id: 't1',
        status: 'completed',
        created_at: '2026-07-31T00:00:00Z',
      },
    ];
    const merged = reconcileTranscript(server, local);
    expect(merged).toHaveLength(1);
    expect(merged[0]?.content).toBe('hello from model');
    expect(merged[0]?.id).toBe('srv-1');
  });

  it('keeps user and assistant as separate bubbles for same turn_id', () => {
    const user = buildOptimisticUserBubbles([
      { turnId: 't1', target: 'alice', content: '@alice hi' },
    ]);
    const both = upsertAssistantBubble(user, {
      turnId: 't1',
      target: 'alice',
      status: 'completed',
      text: 'reply',
      thinking: '',
    });
    expect(both).toHaveLength(2);
    expect(both.map((m) => m.role)).toEqual(['user', 'assistant']);
  });
});
