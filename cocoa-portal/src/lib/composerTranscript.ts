/**
 * Composer transcript merge helpers — keep user and assistant bubbles independent.
 */

export type TranscriptMessage = {
  readonly id: string;
  readonly role: string;
  readonly content: string;
  readonly target_entity: string | null;
  /** Prefer display_name (大名); falls back to slug — same as Lost One labels. */
  readonly target_entity_name?: string | null;
  readonly turn_id: string | null;
  readonly status: string;
  readonly author_user_id?: string | null;
  readonly author_username?: string | null;
  readonly author_nickname?: string | null;
  /** Prefer nickname; falls back to username — aligned with display_name → slug. */
  readonly author_display_name?: string | null;
  /** Human recipient for assistant replies (same-turn user author). */
  readonly recipient_username?: string | null;
  readonly recipient_nickname?: string | null;
  readonly recipient_display_name?: string | null;
  readonly created_at: string | null;
  readonly instance_id?: string | null;
};

export type StreamLane = {
  readonly turnId: string;
  readonly target: string;
  readonly targetName?: string | null;
  readonly recipientUsername?: string | null;
  readonly recipientDisplayName?: string | null;
  status: 'responding' | 'completed' | 'failed';
  text: string;
  thinking: string;
  error?: string;
};

/** Prefer nickname (大名), then username (slug-like) — mirrors entity display_name → slug. */
export function userDisplayLabel(
  nickname: string | null | undefined,
  username: string | null | undefined,
): string {
  const nick = nickname?.trim();
  if (nick) return nick;
  return username?.trim() || '';
}

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
      target_entity_name: lane.targetName ?? existing.target_entity_name ?? null,
      recipient_username: lane.recipientUsername ?? existing.recipient_username ?? null,
      recipient_display_name:
        lane.recipientDisplayName ?? existing.recipient_display_name ?? null,
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
      target_entity_name: lane.targetName ?? null,
      turn_id: lane.turnId,
      status,
      author_user_id: null,
      author_username: null,
      author_nickname: null,
      author_display_name: null,
      recipient_username: lane.recipientUsername ?? null,
      recipient_nickname: null,
      recipient_display_name: lane.recipientDisplayName ?? null,
      created_at: new Date().toISOString(),
    },
  ];
}

export function buildOptimisticUserBubbles(
  deliveries: readonly {
    turnId: string;
    target: string;
    targetName?: string | null;
    content: string;
    authorUsername?: string | null;
    authorNickname?: string | null;
  }[],
): TranscriptMessage[] {
  const now = new Date().toISOString();
  return deliveries.map((d) => {
    const authorUsername = d.authorUsername ?? null;
    const authorNickname = d.authorNickname ?? null;
    return {
      id: `local-user-${d.turnId}`,
      role: 'user',
      content: d.content,
      target_entity: d.target,
      target_entity_name: d.targetName ?? null,
      turn_id: d.turnId,
      status: 'completed',
      author_user_id: null,
      author_username: authorUsername,
      author_nickname: authorNickname,
      author_display_name: userDisplayLabel(authorNickname, authorUsername) || null,
      recipient_username: null,
      recipient_nickname: null,
      recipient_display_name: null,
      created_at: now,
    };
  });
}
