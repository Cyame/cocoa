/**
 * Eyot Instance Host entrypoint.
 * Connects outbound to Backend Tunnel and drives `pi --mode rpc`.
 */

import http from "node:http";
import { ChatBridge } from "./chat-bridge.js";
import { PiRpc } from "./pi-rpc.js";
import type { TunnelMessage } from "./protocol.js";
import { TunnelClient } from "./tunnel-client.js";
import { materializeAgentBundle } from "./workspace-bootstrap.js";

function requireEnv(name: string): string {
  const v = process.env[name]?.trim();
  if (!v) {
    console.error(`[host] missing required env ${name}`);
    process.exit(1);
  }
  return v;
}

function startHealthz(port: number): http.Server {
  const server = http.createServer((req, res) => {
    if (req.url === "/healthz" || req.url === "/health") {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ status: "ok" }));
      return;
    }
    res.writeHead(404);
    res.end();
  });
  server.listen(port, () => {
    console.log(`[host] healthz on :${port}`);
  });
  return server;
}

async function main(): Promise<void> {
  const apiUrl = process.env.COCOA_API_URL?.trim() || "http://127.0.0.1:4510";
  const instanceId = requireEnv("COCOA_INSTANCE_ID");
  const proxyToken = requireEnv("COCOA_PROXY_TOKEN");
  const tunnelOverride = process.env.COCOA_TUNNEL_URL?.trim();
  const workspace = process.env.COCOA_WORKSPACE_PATH?.trim() || "/data";
  const healthPort = Number(process.env.COCOA_HOST_PORT || "8080");

  console.log("[host] starting", { instanceId, apiUrl, workspace });

  materializeAgentBundle(workspace, (m, ...a) => console.log(`[host] ${m}`, ...a));

  const health = startHealthz(healthPort);

  const pi = new PiRpc({
    cwd: workspace,
    extraArgs: ["--approve"],
    log: (m, ...a) => console.log(`[pi-rpc] ${m}`, ...a),
  });

  let bridge: ChatBridge | null = null;
  const onMessage = async (msg: TunnelMessage) => {
    if (!bridge) return;
    await bridge.handleTunnelMessage(msg);
  };

  const tunnel = new TunnelClient({
    apiUrl,
    tunnelUrlOverride: tunnelOverride,
    instanceId,
    proxyToken,
    onMessage,
    onAuthOk: () => console.log("[host] tunnel auth.ok"),
    onAuthError: (reason) => console.error("[host] tunnel auth.error", reason),
    log: (m, ...a) => console.log(`[tunnel] ${m}`, ...a),
  });

  bridge = new ChatBridge({
    tunnel,
    pi,
    log: (m, ...a) => console.log(`[chat-bridge] ${m}`, ...a),
  });

  tunnel.start();

  const shutdown = () => {
    console.log("[host] shutting down");
    tunnel.stop();
    pi.kill();
    health.close();
    process.exit(0);
  };
  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);
}

main().catch((err) => {
  console.error("[host] fatal", err);
  process.exit(1);
});
