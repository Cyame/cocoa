/** Tunnel envelope shared with eyot-backend tunnel protocol. */

/**
 * Versioned message types, aligned 1:1 with the backend Tunnel protocol
 * (`eyot-backend/app/services/tunnel/protocol.py`). Dotted names are the
 * wire contract; new message types must follow the same `area.name` shape.
 */
export enum TunnelMessageType {
  // Backend -> Host
  AUTH_OK = "auth.ok",
  AUTH_ERROR = "auth.error",
  CHAT_REQUEST = "chat.request",
  CONTROL = "control",
  PING = "ping",

  // Host -> Backend
  AUTH = "auth",
  CHAT_RESPONSE_CHUNK = "chat.response.chunk",
  CHAT_RESPONSE_DONE = "chat.response.done",
  CHAT_RESPONSE_ERROR = "chat.response.error",
  CHAT_RESPONSE_ACTIVITY = "chat.response.activity",
  PONG = "pong",
}

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
