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
