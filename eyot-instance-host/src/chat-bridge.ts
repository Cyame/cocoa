/** Bridge Tunnel chat.request ↔ pi RPC events → chat.response.*. */

import {
  makeMessage,
  TunnelMessageType,
  type TunnelMessage,
} from "./protocol.js";
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
  replyText: string;
}

function extractAssistantText(evt: PiEvent): string {
  // message_update.text_delta handled separately.
  const ame = evt.assistantMessageEvent as
    | { type?: string; delta?: string; text?: string }
    | undefined;
  if (ame && typeof ame.text === "string" && ame.text) return ame.text;

  if (typeof evt.text === "string" && evt.text) return evt.text;
  if (typeof evt.content === "string" && evt.content) return evt.content;

  const message = evt.message as
    | { role?: string; content?: string | Array<{ type?: string; text?: string }> }
    | undefined;
  if (message && typeof message.content === "string") return message.content;
  if (message && Array.isArray(message.content)) {
    return message.content
      .map((p) => (typeof p?.text === "string" ? p.text : ""))
      .join("");
  }

  const messages = evt.messages as
    | Array<{ role?: string; content?: string }>
    | undefined;
  if (Array.isArray(messages)) {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const m = messages[i];
      if (m?.role === "assistant" && typeof m.content === "string" && m.content) {
        return m.content;
      }
    }
  }
  return "";
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
      this.failActive(err.message || "host_spawn_error");
    });
  }

  async handleTunnelMessage(msg: TunnelMessage): Promise<void> {
    if (msg.type === "chat.request") {
      await this.onChatRequest(msg);
      return;
    }
    if (msg.type === "control") {
      const action = String(msg.payload?.action ?? "");
      // Protocol face only knows "interrupt"; mapping to pi.kill is host-internal.
      if (action === "interrupt") {
        this.log("control.interrupt");
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

    this.active = { turnId, targetEntity, sawText: false, replyText: "" };
    this.log("prompt", turnId, text.slice(0, 80));
    const ok = this.pi.prompt(text || "(empty)", turnId);
    if (!ok) {
      this.sendError(turnId, targetEntity, "host_stdin_closed");
      this.active = null;
    }
  }

  private onPiEvent(evt: PiEvent): void {
    const turn = this.active;
    if (!turn) return;

    if (evt.type === "response") {
      // The bridge only drives one RPC per active turn, so a failed response
      // always means the turn failed; classification must stay runtime-neutral.
      const success = Boolean(evt.success);
      if (!success) {
        const err =
          typeof evt.error === "string"
            ? evt.error
            : JSON.stringify(evt.error ?? "turn_rejected");
        this.sendError(turn.turnId, turn.targetEntity, err);
        this.active = null;
      }
      return;
    }

    if (evt.type === "message_update") {
      const ame = evt.assistantMessageEvent as
        | { type?: string; delta?: string; toolName?: string }
        | undefined;
      if (ame?.type === "text_delta" && typeof ame.delta === "string" && ame.delta) {
        turn.sawText = true;
        turn.replyText += ame.delta;
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
      } else if (ame?.type === "thinking_start" || ame?.type === "thinking_end") {
        this.sendActivity(
          turn,
          "thinking",
          ame.type === "thinking_start" ? "start" : "end",
        );
      } else if (ame?.type === "thinking_delta" && typeof ame.delta === "string") {
        this.sendActivity(turn, "thinking", "delta", { delta: ame.delta });
      } else if (ame?.type === "toolcall_start") {
        this.sendActivity(turn, "tool_use", "start", {
          tool_name: ame.toolName,
        });
      } else if (ame?.type === "toolcall_delta" && typeof ame.delta === "string") {
        this.sendActivity(turn, "tool_use", "delta", { delta: ame.delta });
      } else if (ame?.type === "toolcall_end") {
        this.sendActivity(turn, "tool_use", "end");
      } else {
        // Some pi builds emit full text on message_update without deltas.
        const full = extractAssistantText(evt);
        if (full && full.length > turn.replyText.length) {
          const delta = full.slice(turn.replyText.length);
          turn.sawText = true;
          turn.replyText = full;
          if (delta) {
            this.tunnel.send(
              makeMessage(
                "chat.response.chunk",
                {
                  turn_id: turn.turnId,
                  token: delta,
                  status: "responding",
                  target_entity: turn.targetEntity,
                },
                { turn_id: turn.turnId },
              ),
            );
          }
        }
      }
      return;
    }

    if (evt.type === "message" || evt.type === "agent_message") {
      const full = extractAssistantText(evt);
      if (full && full.length > turn.replyText.length) {
        const delta = full.slice(turn.replyText.length);
        turn.sawText = true;
        turn.replyText = full;
        if (delta) {
          this.tunnel.send(
            makeMessage(
              "chat.response.chunk",
              {
                turn_id: turn.turnId,
                token: delta,
                status: "responding",
                target_entity: turn.targetEntity,
              },
              { turn_id: turn.turnId },
            ),
          );
        }
      }
      return;
    }

    // Tool execution is reported at top level (not nested in message_update).
    if (evt.type === "tool_execution_start") {
      const toolName = String((evt as { toolName?: unknown }).toolName ?? "");
      this.sendActivity(turn, "tool_use", "start", { tool_name: toolName });
      return;
    }
    if (evt.type === "tool_execution_update") {
      const partial = (evt as { partialResult?: unknown }).partialResult;
      const delta =
        typeof partial === "string"
          ? partial
          : partial != null
            ? JSON.stringify(partial)
            : undefined;
      this.sendActivity(turn, "tool_use", "delta", {
        tool_name: String((evt as { toolName?: unknown }).toolName ?? ""),
        ...(delta !== undefined ? { delta } : {}),
      });
      return;
    }
    if (evt.type === "tool_execution_end") {
      this.sendActivity(turn, "tool_use", "end", {
        tool_name: String((evt as { toolName?: unknown }).toolName ?? ""),
      });
      return;
    }

    if (evt.type === "agent_end") {
      // Last chance: pull final assistant text if no deltas were streamed.
      if (!turn.sawText) {
        const full = extractAssistantText(evt);
        if (full) {
          turn.replyText = full;
          turn.sawText = true;
          this.tunnel.send(
            makeMessage(
              "chat.response.chunk",
              {
                turn_id: turn.turnId,
                token: full,
                status: "responding",
                target_entity: turn.targetEntity,
              },
              { turn_id: turn.turnId },
            ),
          );
        }
      }
      this.tunnel.send(
        makeMessage(
          "chat.response.done",
          {
            turn_id: turn.turnId,
            status: "completed",
            target_entity: turn.targetEntity,
            text: turn.replyText,
          },
          { turn_id: turn.turnId },
        ),
      );
      this.active = null;
      return;
    }

    // Some pi builds emit top-level errors
    if (evt.type === "error" || evt.type === "agent_error") {
      const message = String(evt.message ?? evt.error ?? "host_error");
      this.sendError(turn.turnId, turn.targetEntity, message);
      this.active = null;
    }
  }

  private sendActivity(
    turn: ActiveTurn,
    kind: "thinking" | "tool_use",
    status: "start" | "delta" | "end",
    extra: { tool_name?: string; delta?: string } = {},
  ): void {
    this.tunnel.send(
      makeMessage(
        TunnelMessageType.CHAT_RESPONSE_ACTIVITY,
        {
          turn_id: turn.turnId,
          kind,
          status,
          ...extra,
          target_entity: turn.targetEntity,
        },
        { turn_id: turn.turnId },
      ),
    );
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
