/** Outbound WebSocket Tunnel client with exponential backoff reconnect. */

import WebSocket from "ws";
import { deriveTunnelUrl, makeMessage, type TunnelMessage } from "./protocol.js";

const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;

export type TunnelHandler = (msg: TunnelMessage) => void | Promise<void>;

export interface TunnelClientOptions {
  apiUrl: string;
  tunnelUrlOverride?: string;
  instanceId: string;
  proxyToken: string;
  onMessage: TunnelHandler;
  onAuthOk?: () => void;
  onAuthError?: (reason: string) => void;
  log?: (msg: string, ...args: unknown[]) => void;
}

export class TunnelClient {
  private ws: WebSocket | NoneWs = null;
  private stopped = false;
  private attempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly opts: TunnelClientOptions;
  private readonly log: (msg: string, ...args: unknown[]) => void;

  constructor(opts: TunnelClientOptions) {
    this.opts = opts;
    this.log = opts.log ?? ((m, ...a) => console.log(`[tunnel] ${m}`, ...a));
  }

  start(): void {
    this.stopped = false;
    this.connect();
  }

  stop(): void {
    this.stopped = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      try {
        this.ws.close(1000, "host_stop");
      } catch {
        /* ignore */
      }
      this.ws = null;
    }
  }

  send(msg: TunnelMessage): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify(msg));
    return true;
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  private connect(): void {
    if (this.stopped) return;
    const url = deriveTunnelUrl(this.opts.apiUrl, this.opts.tunnelUrlOverride);
    this.log("connecting", url);
    const ws = new WebSocket(url);
    this.ws = ws;

    ws.on("open", () => {
      this.attempt = 0;
      const auth = makeMessage("auth", {
        instance_id: this.opts.instanceId,
        proxy_token: this.opts.proxyToken,
      });
      ws.send(JSON.stringify(auth));
      this.log("auth sent");
    });

    ws.on("message", (data) => {
      void this.handleRaw(String(data));
    });

    ws.on("close", (code, reason) => {
      this.log("closed", code, reason.toString());
      this.ws = null;
      this.scheduleReconnect();
    });

    ws.on("error", (err) => {
      this.log("error", err.message);
    });
  }

  private async handleRaw(raw: string): Promise<void> {
    let msg: TunnelMessage;
    try {
      msg = JSON.parse(raw) as TunnelMessage;
    } catch {
      this.log("bad json", raw.slice(0, 200));
      return;
    }

    if (msg.type === "auth.ok") {
      this.log("auth.ok");
      this.opts.onAuthOk?.();
      return;
    }
    if (msg.type === "auth.error") {
      const reason = String(msg.payload?.reason ?? "unknown");
      this.log("auth.error", reason);
      this.opts.onAuthError?.(reason);
      return;
    }
    if (msg.type === "ping") {
      this.send(makeMessage("pong", {}));
      return;
    }

    try {
      await this.opts.onMessage(msg);
    } catch (err) {
      this.log("handler error", err);
    }
  }

  private scheduleReconnect(): void {
    if (this.stopped) return;
    const delay = Math.min(
      RECONNECT_MAX_MS,
      RECONNECT_BASE_MS * 2 ** Math.min(this.attempt, 5),
    );
    this.attempt += 1;
    this.log("reconnect in ms", delay, "attempt", this.attempt);
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }
}

type NoneWs = null;
