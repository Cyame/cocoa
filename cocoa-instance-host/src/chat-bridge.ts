/** Bridge Tunnel chat.request ↔ pi RPC events → chat.response.*. */

import { makeMessage, type TunnelMessage } from "./protocol.js";
import type { PiEvent, PiRpc } from "./pi-rpc.js";
import type { TunnelClient } from "./tunnel-client.js";

export interface ChatBridgeOptions {
  tunnel: TunnelClient;
  pi: PiRpc;
  log?: (msg: string, ...args: unknown[]) => void;
}

interface ActiveTurn {
  turnId: string;
  targetEntity?: string;
  sawText: boolean;
}

export class ChatBridge {
  private readonly tunnel: TunnelClient;
  private readonly pi: PiRpc;
  private readonly log: (msg: string, ...args: unknown[]) => void;
  private active: ActiveTurn | null = null;

  constructor(opts: ChatBridgeOptions) {
    this.tunnel = opts.tunnel;
    this.pi = opts.pi;
    this.log = opts.log ?? ((m, ...a) => console.log(`[chat-bridge] ${m}`, ...a));
    this.pi.on("event", (evt: PiEvent) => {
      void this.onPiEvent(evt);
    });
    this.pi.on("error", (err: Error) => {
      this.failActive(err.message || "pi_spawn_error");
    });
  }

  async handleTunnelMessage(msg: TunnelMessage): Promise<void> {
    if (msg.type === "chat.request") {
      await this.onChatRequest(msg);
      return;
    }
    if (msg.type === "control") {
      const action = String(msg.payload?.action ?? "");
      if (action === "kill") {
        this.log("control.kill");
        this.pi.kill();
      }
    }
  }

  private async onChatRequest(msg: TunnelMessage): Promise<void> {
    const turnId = String(msg.turn_id ?? msg.payload.turn_id ?? "");
    const text = String(msg.payload.text ?? "");
    const targetEntity =
      msg.payload.target_entity != null
        ? String(msg.payload.target_entity)
        : undefined;

    if (!turnId) {
      this.log("chat.request missing turn_id");
      return;
    }

    if (!this.pi.running) {
      try {
        this.pi.start();
      } catch (err) {
        this.sendError(turnId, targetEntity, String(err));
        return;
      }
    }

    this.active = { turnId, targetEntity, sawText: false };
    this.log("prompt", turnId, text.slice(0, 80));
    const ok = this.pi.prompt(text || "(empty)", turnId);
    if (!ok) {
      this.sendError(turnId, targetEntity, "pi_stdin_closed");
      this.active = null;
    }
  }

  private onPiEvent(evt: PiEvent): void {
    const turn = this.active;
    if (!turn) return;

    if (evt.type === "response") {
      const success = Boolean(evt.success);
      if (!success && evt.command === "prompt") {
        const err =
          typeof evt.error === "string"
            ? evt.error
            : JSON.stringify(evt.error ?? "prompt_rejected");
        this.sendError(turn.turnId, turn.targetEntity, err);
        this.active = null;
      }
      return;
    }

    if (evt.type === "message_update") {
      const ame = evt.assistantMessageEvent as
        | { type?: string; delta?: string }
        | undefined;
      if (ame?.type === "text_delta" && typeof ame.delta === "string" && ame.delta) {
        turn.sawText = true;
        this.tunnel.send(
          makeMessage(
            "chat.response.chunk",
            {
              turn_id: turn.turnId,
              token: ame.delta,
              status: "responding",
              target_entity: turn.targetEntity,
            },
            { turn_id: turn.turnId },
          ),
        );
      }
      return;
    }

    if (evt.type === "agent_end") {
      this.tunnel.send(
        makeMessage(
          "chat.response.done",
          {
            turn_id: turn.turnId,
            finish_reason: "stop",
            status: "completed",
            target_entity: turn.targetEntity,
          },
          { turn_id: turn.turnId },
        ),
      );
      this.active = null;
      return;
    }

    // Some pi builds emit top-level errors
    if (evt.type === "error" || evt.type === "agent_error") {
      const message = String(evt.message ?? evt.error ?? "pi_error");
      this.sendError(turn.turnId, turn.targetEntity, message);
      this.active = null;
    }
  }

  private failActive(message: string): void {
    if (!this.active) return;
    this.sendError(this.active.turnId, this.active.targetEntity, message);
    this.active = null;
  }

  private sendError(
    turnId: string,
    targetEntity: string | undefined,
    message: string,
  ): void {
    this.log("error", turnId, message);
    this.tunnel.send(
      makeMessage(
        "chat.response.error",
        {
          turn_id: turnId,
          message,
          status: "failed",
          target_entity: targetEntity,
        },
        { turn_id: turnId },
      ),
    );
  }
}
