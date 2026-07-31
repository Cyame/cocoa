/**
 * Composer transcript merge helpers — keep user and assistant bubbles independent.
 */

export type TranscriptMessage = {
  readonly id: string;
  readonly role: string;
  readonly content: string;
  readonly target_entity: string | null;
  readonly turn_id: string | null;
  readonly status: string;
  readonly author_user_id?: string | null;
  readonly author_username?: string | null;
  readonly created_at: string | null;
  readonly instance_id?: string | null;
};

export type StreamLane = {
  readonly turnId: string;
  readonly target: string;
  status: 'responding' | 'completed' | 'failed';
  text: string;
  thinking: string;
  error?: string;
};

function roleTurnKey(role: string, turnId: string): string {
  return `${role}:${turnId}`;
}

/** Prefer non-empty local content when server reload races ahead of finalize. */
export function reconcileTranscript(
  server: readonly TranscriptMessage[],
  local: readonly TranscriptMessage[],
): TranscriptMessage[] {
  const localByKey = new Map<string, TranscriptMessage>();
  for (const msg of local) {
    if (msg.turn_id && msg.content.trim()) {
      localByKey.set(roleTurnKey(msg.role, msg.turn_id), msg);
    }
  }

  const seenIds = new Set<string>();
  const seenKeys = new Set<string>();
  const out: TranscriptMessage[] = server.map((msg) => {
    seenIds.add(msg.id);
    if (!msg.turn_id) return msg;
    const key = roleTurnKey(msg.role, msg.turn_id);
    seenKeys.add(key);
    const localMsg = localByKey.get(key);
    if (!localMsg) return msg;
    if (msg.content.trim().length >= localMsg.content.trim().length) return msg;
    return { ...msg, content: localMsg.content, status: msg.status || localMsg.status };
  });

  for (const msg of local) {
    if (seenIds.has(msg.id)) continue;
    if (msg.turn_id) {
      const key = roleTurnKey(msg.role, msg.turn_id);
      if (seenKeys.has(key)) continue;
      const onServer = server.some(
        (s) => s.role === msg.role && s.turn_id === msg.turn_id,
      );
      if (onServer) continue;
    }
    out.push(msg);
  }
  return out;
}

export function upsertAssistantBubble(
  prev: readonly TranscriptMessage[],
  lane: StreamLane,
): TranscriptMessage[] {
  const content = lane.error?.trim() ? lane.error : lane.text;
  const status =
    lane.status === 'responding' ? 'responding' : lane.status === 'failed' ? 'failed' : 'completed';
  const idx = prev.findIndex((m) => m.role === 'assistant' && m.turn_id === lane.turnId);
  if (idx >= 0) {
    const existing = prev[idx];
    const nextContent =
      content.trim().length >= (existing.content?.trim().length ?? 0) ? content : existing.content;
    const copy = [...prev];
    copy[idx] = {
      ...existing,
      content: nextContent,
      status,
      target_entity: lane.target || existing.target_entity,
    };
    return copy;
  }
  return [
    ...prev,
    {
      id: `local-assistant-${lane.turnId}`,
      role: 'assistant',
      content,
      target_entity: lane.target,
      turn_id: lane.turnId,
      status,
      author_user_id: null,
      author_username: null,
      created_at: new Date().toISOString(),
    },
  ];
}

export function buildOptimisticUserBubbles(
  deliveries: readonly {
    turnId: string;
    target: string;
    content: string;
  }[],
): TranscriptMessage[] {
  const now = new Date().toISOString();
  return deliveries.map((d) => ({
    id: `local-user-${d.turnId}`,
    role: 'user',
    content: d.content,
    target_entity: d.target,
    turn_id: d.turnId,
    status: 'completed',
    author_user_id: null,
    author_username: null,
    created_at: now,
  }));
}
