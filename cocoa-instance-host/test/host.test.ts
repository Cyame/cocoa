import assert from "node:assert/strict";
import { createServer } from "node:http";
import { once } from "node:events";
import test from "node:test";
import { WebSocketServer } from "ws";
import { ChatBridge } from "../src/chat-bridge.js";
import { deriveTunnelUrl, makeMessage } from "../src/protocol.js";
import { PiRpc } from "../src/pi-rpc.js";
import { TunnelClient } from "../src/tunnel-client.js";

test("deriveTunnelUrl maps http to ws path", () => {
  assert.equal(
    deriveTunnelUrl("http://cocoa-backend:4510"),
    "ws://cocoa-backend:4510/api/v1/tunnel/connect",
  );
  assert.equal(
    deriveTunnelUrl("http://x", "ws://override/tunnel"),
    "ws://override/tunnel",
  );
});

test("tunnel client auths and receives chat.request", async () => {
  const server = createServer();
  const wss = new WebSocketServer({ server, path: "/api/v1/tunnel/connect" });
  const port = await new Promise<number>((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      assert.ok(addr && typeof addr === "object");
      resolve(addr.port);
    });
  });

  const gotAuth = once(wss, "connection").then(async ([socket]) => {
    const [raw] = await once(socket, "message");
    const msg = JSON.parse(String(raw));
    assert.equal(msg.type, "auth");
    assert.equal(msg.payload.instance_id, "inst-1");
    socket.send(
      JSON.stringify(makeMessage("auth.ok", { instance_id: "inst-1" })),
    );
    socket.send(
      JSON.stringify(
        makeMessage(
          "chat.request",
          { turn_id: "t1", text: "hi", target_entity: "e" },
          { turn_id: "t1" },
        ),
      ),
    );
  });

  const messages: string[] = [];
  const client = new TunnelClient({
    apiUrl: `http://127.0.0.1:${port}`,
    instanceId: "inst-1",
    proxyToken: "tok",
    onMessage: async (msg) => {
      messages.push(msg.type);
    },
    log: () => {},
  });
  client.start();
  await gotAuth;
  await new Promise((r) => setTimeout(r, 80));
  assert.ok(messages.includes("chat.request"));
  client.stop();
  await new Promise<void>((resolve) => wss.close(() => resolve()));
  await new Promise<void>((resolve) => server.close(() => resolve()));
});

test("chat bridge maps pi text_delta to chunk and agent_end to done", async () => {
  const sent: Array<{ type: string; payload: Record<string, unknown> }> = [];
  const fakeTunnel = {
    send(msg: { type: string; payload: Record<string, unknown> }) {
      sent.push(msg);
      return true;
    },
  };
  const fakePi = new PiRpc({ log: () => {} });
  Object.defineProperty(fakePi, "running", { get: () => true });
  fakePi.prompt = () => true;
  fakePi.start = () => {};

  const bridge = new ChatBridge({
    tunnel: fakeTunnel as unknown as TunnelClient,
    pi: fakePi,
    log: () => {},
  });

  await bridge.handleTunnelMessage(
    makeMessage(
      "chat.request",
      { turn_id: "turn-a", text: "hello", target_entity: "alice" },
      { turn_id: "turn-a" },
    ),
  );

  fakePi.emit("event", {
    type: "message_update",
    assistantMessageEvent: { type: "text_delta", delta: "你好" },
  });
  fakePi.emit("event", { type: "agent_end" });

  assert.equal(sent[0]?.type, "chat.response.chunk");
  assert.equal(sent[0]?.payload.token, "你好");
  assert.equal(sent[1]?.type, "chat.response.done");
});

test("chat bridge falls back to agent_end message text when no deltas", async () => {
  const sent: Array<{ type: string; payload: Record<string, unknown> }> = [];
  const fakeTunnel = {
    send(msg: { type: string; payload: Record<string, unknown> }) {
      sent.push(msg);
      return true;
    },
  };
  const fakePi = new PiRpc({ log: () => {} });
  Object.defineProperty(fakePi, "running", { get: () => true });
  fakePi.prompt = () => true;
  fakePi.start = () => {};

  const bridge = new ChatBridge({
    tunnel: fakeTunnel as unknown as TunnelClient,
    pi: fakePi,
    log: () => {},
  });

  await bridge.handleTunnelMessage(
    makeMessage(
      "chat.request",
      { turn_id: "turn-b", text: "hello", target_entity: "alice" },
      { turn_id: "turn-b" },
    ),
  );

  fakePi.emit("event", {
    type: "agent_end",
    messages: [{ role: "assistant", content: "最终答复" }],
  });

  assert.equal(sent[0]?.type, "chat.response.chunk");
  assert.equal(sent[0]?.payload.token, "最终答复");
  assert.equal(sent[1]?.type, "chat.response.done");
  assert.equal(sent[1]?.payload.text, "最终答复");
});

test("chat bridge maps control.interrupt to pi.kill (no tunnel send)", async () => {
  const sent: Array<{ type: string; payload: Record<string, unknown> }> = [];
  const fakeTunnel = {
    send(msg: { type: string; payload: Record<string, unknown> }) {
      sent.push(msg);
      return true;
    },
  };
  const fakePi = new PiRpc({ log: () => {} });
  Object.defineProperty(fakePi, "running", { get: () => true });
  let kills = 0;
  fakePi.kill = () => {
    kills += 1;
  };

  const bridge = new ChatBridge({
    tunnel: fakeTunnel as unknown as TunnelClient,
    pi: fakePi,
    log: () => {},
  });

  await bridge.handleTunnelMessage(
    makeMessage("control", { action: "interrupt" }),
  );
  assert.equal(kills, 1, "interrupt must kill the pi process");
  assert.equal(sent.length, 0, "interrupt is host-internal, no tunnel frame");

  // Unrelated control actions must not touch the process.
  await bridge.handleTunnelMessage(makeMessage("control", { action: "nudge" }));
  assert.equal(kills, 1, "unknown control action must not kill pi");
});

test("chat bridge done payload carries no finish_reason", async () => {
  const sent: Array<{ type: string; payload: Record<string, unknown> }> = [];
  const fakeTunnel = {
    send(msg: { type: string; payload: Record<string, unknown> }) {
      sent.push(msg);
      return true;
    },
  };
  const fakePi = new PiRpc({ log: () => {} });
  Object.defineProperty(fakePi, "running", { get: () => true });
  fakePi.prompt = () => true;
  fakePi.start = () => {};

  const bridge = new ChatBridge({
    tunnel: fakeTunnel as unknown as TunnelClient,
    pi: fakePi,
    log: () => {},
  });

  await bridge.handleTunnelMessage(
    makeMessage(
      "chat.request",
      { turn_id: "turn-c", text: "hello", target_entity: "alice" },
      { turn_id: "turn-c" },
    ),
  );
  fakePi.emit("event", { type: "agent_end" });

  const done = sent.find((m) => m.type === "chat.response.done");
  assert.ok(done, "expected a done frame");
  assert.equal(done.payload.status, "completed");
  assert.equal(done.payload.turn_id, "turn-c");
  assert.ok(
    !("finish_reason" in done.payload),
    "Tunnel done frame must not expose finish_reason",
  );
  assert.deepEqual(Object.keys(done.payload).sort(), [
    "status",
    "target_entity",
    "text",
    "turn_id",
  ]);
});

test("chat bridge error codes are runtime-neutral (no pi RPC names)", async () => {
  const sent: Array<{ type: string; payload: Record<string, unknown> }> = [];
  const fakeTunnel = {
    send(msg: { type: string; payload: Record<string, unknown> }) {
      sent.push(msg);
      return true;
    },
  };
  const fakePi = new PiRpc({ log: () => {} });
  Object.defineProperty(fakePi, "running", { get: () => true });
  fakePi.start = () => {};
  fakePi.prompt = () => true;

  const bridge = new ChatBridge({
    tunnel: fakeTunnel as unknown as TunnelClient,
    pi: fakePi,
    log: () => {},
  });
  const startTurn = async (turnId: string) => {
    sent.length = 0; // reset before the request so request-time errors are captured
    await bridge.handleTunnelMessage(
      makeMessage("chat.request", { turn_id: turnId, text: "hi" }, { turn_id: turnId }),
    );
  };
  const allErrorCodes: string[] = [];
  const lastError = () => {
    const err = sent.find((m) => m.type === "chat.response.error");
    assert.ok(err, "expected a chat.response.error frame");
    const message = String(err.payload.message ?? "");
    allErrorCodes.push(message);
    return message;
  };

  // pi spawn error (emitter "error" without message) -> host_spawn_error
  await startTurn("t-spawn");
  fakePi.emit("error", new Error(""));
  assert.equal(lastError(), "host_spawn_error");

  // prompt() returned false (stdin not writable) -> host_stdin_closed
  fakePi.prompt = () => false;
  await startTurn("t-stdin");
  assert.equal(lastError(), "host_stdin_closed");

  // response success=false without error payload -> turn_rejected
  // (bridge JSON-stringifies the fallback, so match the neutral code loosely)
  fakePi.prompt = () => true;
  await startTurn("t-reject");
  fakePi.emit("event", { type: "response", success: false });
  const rejectedMsg = lastError();
  assert.ok(rejectedMsg.includes("turn_rejected"), `got ${rejectedMsg}`);
  assert.ok(!rejectedMsg.includes("prompt_rejected"), `got ${rejectedMsg}`);

  // top-level agent_error without fields -> host_error
  await startTurn("t-error");
  fakePi.emit("event", { type: "agent_error" });
  assert.equal(lastError(), "host_error");

  // Contract: no leaked pi RPC command names anywhere in Tunnel error codes.
  const leaked = ["pi_spawn_error", "pi_stdin_closed", "prompt_rejected", "pi_error"];
  for (const code of allErrorCodes) {
    for (const name of leaked) {
      assert.ok(!code.includes(name), `error code must not contain leaked name '${name}': ${code}`);
    }
  }
});

test("pi rpc framing splits only on LF", () => {
  class TestRpc extends PiRpc {
    feed(s: string) {
      (this as unknown as { buffer: string }).buffer += s;
      (this as unknown as { drain: () => void }).drain();
    }
  }
  const events: unknown[] = [];
  const t = new TestRpc({ log: () => {} });
  t.on("event", (e) => events.push(e));
  t.feed(
    `${JSON.stringify({
      type: "message_update",
      assistantMessageEvent: { type: "text_delta", delta: "x" },
    })}\n`,
  );
  assert.equal((events[0] as { type: string }).type, "message_update");
});

test("chat bridge maps thinking events to chat.response.activity kind=thinking", async () => {
  const sent: Array<{ type: string; payload: Record<string, unknown> }> = [];
  const fakeTunnel = {
    send(msg: { type: string; payload: Record<string, unknown> }) {
      sent.push(msg);
      return true;
    },
  };
  const fakePi = new PiRpc({ log: () => {} });
  Object.defineProperty(fakePi, "running", { get: () => true });
  fakePi.prompt = () => true;
  fakePi.start = () => {};

  const bridge = new ChatBridge({
    tunnel: fakeTunnel as unknown as TunnelClient,
    pi: fakePi,
    log: () => {},
  });

  await bridge.handleTunnelMessage(
    makeMessage(
      "chat.request",
      { turn_id: "turn-think", text: "hello", target_entity: "alice" },
      { turn_id: "turn-think" },
    ),
  );

  fakePi.emit("event", {
    type: "message_update",
    assistantMessageEvent: { type: "thinking_start", contentIndex: 0 },
  });
  fakePi.emit("event", {
    type: "message_update",
    assistantMessageEvent: {
      type: "thinking_delta",
      contentIndex: 0,
      delta: "深入思考",
    },
  });
  fakePi.emit("event", {
    type: "message_update",
    assistantMessageEvent: { type: "thinking_end", contentIndex: 0 },
  });

  const activities = sent.filter((m) => m.type === "chat.response.activity");
  assert.equal(activities.length, 3);
  assert.deepEqual(activities[0]?.payload, {
    turn_id: "turn-think",
    kind: "thinking",
    status: "start",
    target_entity: "alice",
  });
  assert.deepEqual(activities[1]?.payload, {
    turn_id: "turn-think",
    kind: "thinking",
    status: "delta",
    delta: "深入思考",
    target_entity: "alice",
  });
  assert.deepEqual(activities[2]?.payload, {
    turn_id: "turn-think",
    kind: "thinking",
    status: "end",
    target_entity: "alice",
  });
  assert.equal(
    sent.some((m) => m.type === "chat.response.chunk"),
    false,
    "thinking events must not leak into text chunk frames",
  );
});

test("chat bridge maps toolcall_start to activity kind=tool_use with tool_name", async () => {
  const sent: Array<{ type: string; payload: Record<string, unknown> }> = [];
  const fakeTunnel = {
    send(msg: { type: string; payload: Record<string, unknown> }) {
      sent.push(msg);
      return true;
    },
  };
  const fakePi = new PiRpc({ log: () => {} });
  Object.defineProperty(fakePi, "running", { get: () => true });
  fakePi.prompt = () => true;
  fakePi.start = () => {};

  const bridge = new ChatBridge({
    tunnel: fakeTunnel as unknown as TunnelClient,
    pi: fakePi,
    log: () => {},
  });

  await bridge.handleTunnelMessage(
    makeMessage(
      "chat.request",
      { turn_id: "turn-tool", text: "hello", target_entity: "alice" },
      { turn_id: "turn-tool" },
    ),
  );

  fakePi.emit("event", {
    type: "message_update",
    assistantMessageEvent: {
      type: "toolcall_start",
      contentIndex: 0,
      id: "call_1",
      toolName: "bash",
    },
  });
  fakePi.emit("event", {
    type: "message_update",
    assistantMessageEvent: {
      type: "toolcall_delta",
      contentIndex: 0,
      delta: '{"command":"ls"}',
    },
  });
  fakePi.emit("event", {
    type: "message_update",
    assistantMessageEvent: { type: "toolcall_end", contentIndex: 0 },
  });

  const activities = sent.filter((m) => m.type === "chat.response.activity");
  assert.equal(activities.length, 3);
  assert.deepEqual(activities[0]?.payload, {
    turn_id: "turn-tool",
    kind: "tool_use",
    status: "start",
    tool_name: "bash",
    target_entity: "alice",
  });
  assert.deepEqual(activities[1]?.payload, {
    turn_id: "turn-tool",
    kind: "tool_use",
    status: "delta",
    delta: '{"command":"ls"}',
    target_entity: "alice",
  });
  assert.deepEqual(activities[2]?.payload, {
    turn_id: "turn-tool",
    kind: "tool_use",
    status: "end",
    target_entity: "alice",
  });
});

test("chat bridge maps top-level tool_execution_start to tool_use activity", async () => {
  const sent: Array<{ type: string; payload: Record<string, unknown> }> = [];
  const fakeTunnel = {
    send(msg: { type: string; payload: Record<string, unknown> }) {
      sent.push(msg);
      return true;
    },
  };
  const fakePi = new PiRpc({ log: () => {} });
  Object.defineProperty(fakePi, "running", { get: () => true });
  fakePi.prompt = () => true;
  fakePi.start = () => {};

  const bridge = new ChatBridge({
    tunnel: fakeTunnel as unknown as TunnelClient,
    pi: fakePi,
    log: () => {},
  });

  await bridge.handleTunnelMessage(
    makeMessage(
      "chat.request",
      { turn_id: "turn-exec", text: "delegate", target_entity: "alice" },
      { turn_id: "turn-exec" },
    ),
  );

  fakePi.emit("event", {
    type: "tool_execution_start",
    toolCallId: "call_1",
    toolName: "subagent-ops",
    args: { strategy: "default" },
  });

  const activities = sent.filter((m) => m.type === "chat.response.activity");
  assert.equal(activities.length, 1);
  assert.deepEqual(activities[0]?.payload, {
    turn_id: "turn-exec",
    kind: "tool_use",
    status: "start",
    tool_name: "subagent-ops",
    target_entity: "alice",
  });
});
