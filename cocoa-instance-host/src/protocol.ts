/** Tunnel envelope shared with cocoa-backend tunnel protocol. */

export interface TunnelMessage {
  id: string;
  type: string;
  reply_to?: string;
  turn_id?: string;
  payload: Record<string, unknown>;
  ts: number;
}

export function newId(): string {
  return crypto.randomUUID();
}

export function makeMessage(
  type: string,
  payload: Record<string, unknown> = {},
  extra: Partial<Pick<TunnelMessage, "reply_to" | "turn_id">> = {},
): TunnelMessage {
  return {
    id: newId(),
    type,
    payload,
    ts: Date.now(),
    ...extra,
  };
}

export function httpToWs(url: string): string {
  return url
    .replace(/^https:\/\//i, "wss://")
    .replace(/^http:\/\//i, "ws://")
    .replace(/\/+$/, "");
}

export function deriveTunnelUrl(apiUrl: string, override?: string): string {
  if (override && override.trim()) {
    return override.trim().replace(/\/+$/, "");
  }
  return `${httpToWs(apiUrl)}/api/v1/tunnel/connect`;
}
