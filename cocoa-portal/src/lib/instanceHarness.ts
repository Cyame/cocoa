import type { Event, InjectDeliveryMode, InjectKind, InjectPayload } from '@/lib/types';

export const HARNESS_EVENTS_LIMIT = 20;

export type HarnessEventPage = {
  readonly items: readonly Event[];
  readonly next_cursor: string | null;
  readonly total: number | null;
};

/**
 * Mirrors DebugPage.buildEventsPath (L56-68), narrowed to the two
 * parameters the instance detail panel needs.
 */
export function buildInstanceEventsPath(
  instanceId: string,
  typePrefix: string,
  limit: number = HARNESS_EVENTS_LIMIT,
): string {
  const params = new URLSearchParams();
  params.set('limit', String(limit));
  params.set('type_prefix', typePrefix);
  params.set('resource_id', instanceId);
  return `/events?${params.toString()}`;
}

/** Merge inject + report pages: dedupe by id, newest first. */
export function mergeHarnessEvents(
  injectEvents: readonly Event[],
  reportEvents: readonly Event[],
  limit: number = HARNESS_EVENTS_LIMIT,
): readonly Event[] {
  const byId = new Map<string, Event>();
  for (const event of [...injectEvents, ...reportEvents]) {
    byId.set(event.id, event);
  }
  return [...byId.values()]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, limit);
}

/** Trim tldr and omit it when blank so the backend never sees empty strings. */
export function buildInjectPayload(input: {
  readonly kind: InjectKind;
  readonly deliveryMode: InjectDeliveryMode;
  readonly tldr: string;
}): InjectPayload {
  const tldr = input.tldr.trim();
  return {
    kind: input.kind,
    delivery_mode: input.deliveryMode,
    ...(tldr.length > 0 ? { tldr } : {}),
  };
}
