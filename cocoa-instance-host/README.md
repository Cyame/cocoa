# Cocoa Instance Host — Tunnel WS client + pi RPC bridge (PRD-v3.5)

Outbound WebSocket client that authenticates to Cocoa Backend
`/api/v1/tunnel/connect`, receives `chat.request`, drives
`pi --mode rpc`, and streams `chat.response.chunk|done|error`.

Runtime: **Node >= 24** (Docker base `node:24-bookworm-slim`).

## Env

| Variable | Required | Description |
|---|---|---|
| `COCOA_API_URL` | yes (default localhost) | Backend HTTP base (converted to ws) |
| `COCOA_TUNNEL_URL` | no | Full WS URL override |
| `COCOA_INSTANCE_ID` | yes | Instance UUID |
| `COCOA_PROXY_TOKEN` | yes | Matches `Instance.proxy_token` |
| `COCOA_WORKSPACE_PATH` | no | pi cwd (default `/data`; layout: `.pi/` `work/` `memory/` `shared/`) |
| `COCOA_AGENT_CONFIG_DIR` | no | ConfigMap mount with SYSTEM.md (default `/etc/config`) |
| `PI_MODEL` / `PI_PROVIDER` | no | Passed to `pi --mode rpc` |
| `COCOA_HOST_PORT` | no | healthz port (default 8080) |

## Dev

```bash
cd cocoa-instance-host
npm install
npm run build
COCOA_INSTANCE_ID=... COCOA_PROXY_TOKEN=... npm start
npm test
```
