> **Pre-v4 reference**: Conflict with `.omo/evidence/audit-product-design.md` → audit wins. Awaiting v4 PRD rewrite.
>

# Eyot Runtime System

> **Code rename pending (15d-rename wave)**: This doc describes target architecture (15d+). Current code uses old naming.

The Instance runtime system is Eyot's execution substrate. An Instance is the running embodiment of an Entity within a Workspace — it owns an isolated workspace, consumes configuration from the database, receives messages via the P5 messaging topology, and writes results to the P6 blackboard. P7 delivers the Instance CRUD API, lifecycle state machine, and K8s deployment scaffolding; the control-plane harness arrives in P8.

**Driver lock (2026-07-30):** each 化身 is driven by a sandboxed **pi** agent runtime (React optional). The Workspace control plane (Supervisor / Boulder / Portal) is Eyot's evolution of senpi · oh-my-openagent · oh-my-pi — it is **not** Senpi CLI acting as the Instance driver. Path prefix `.pi/workspace/...` names the Instance filesystem root under that pi-oriented layout; it does not mean "Senpi owns the Workspace product surface."

## 1. Instance Lifecycle Model

Instances move through a directed acyclic graph (DAG) of statuses. Each transition is validated explicitly in the action endpoint — there is no generic PATCH status.

```
creating
   |
   v
deploying
   |
   v
running ──→ restarting ──→ deploying ──→ running
   |                           ^
   |      (restart loop)       |
   └───────────────────────────┘
   |
   v
pending ──→ deleting (soft-delete, 204)

any ──→ failed (fault report)
```

### Status Definitions

| Status | Meaning |
|--------|---------|
| `creating` | Initial state after `POST /instances`. Workspace path and proxy token are assigned. |
| `deploying` | `POST /instances/{id}/deploy` — K8s manifests are being applied (or simulated). |
| `running` | `POST /instances/{id}/start` — agent process is active, receiving messages. |
| `restarting` | `POST /instances/{id}/restart` — instance is cycling (stop then start). |
| `pending` | `POST /instances/{id}/stop` — instance is halted but not deleted; workspace is preserved. |
| `failed` | `POST /instances/{id}/fail` — fault report received; may be restarted. |
| `deleting` | `DELETE /instances/{id}` — soft-delete in progress; workspace PVC is retained until cleanup. |

### Valid Transitions

| Action Endpoint | Allowed From | Target Status |
|-----------------|-------------|---------------|
| `POST .../deploy` | `creating`, `restarting` | `deploying` |
| `POST .../start` | `pending`, `deploying` | `running` |
| `POST .../restart` | `running`, `failed` | `restarting` |
| `POST .../stop` | `running` | `pending` |
| `POST .../fail` | any | `failed` |
| `DELETE ...` | `pending`, `failed`, `creating` | `deleting` |

Invalid transitions return `409 Conflict` with `error_code: "instance.invalid_transition"` and a `details` payload listing `current` status and `expected` allowed statuses.

## 2. Instance CRUD and Action API Reference

All endpoints live under `/api/v1/instances`. Time fields are ISO 8601 UTC. Pagination uses offset-based defaults (`?limit=50&offset=0`).

### CRUD Endpoints

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| `GET` | `/api/v1/instances` | List instances. Filters: `?employee_id=`, `?office_id=`, `?status=` | `200` — paginated list of `InstanceOut` |
| `GET` | `/api/v1/instances/{instance_id}` | Get a single instance | `200` — `InstanceOut`; `404` — not found |
| `POST` | `/api/v1/instances` | Create an instance. Body: `{employee_id, office_id, workspace_path?, runtime_config?}` | `201` — `InstanceOut` |
| `PATCH` | `/api/v1/instances/{instance_id}` | Update `runtime_config` or `workspace_path`. Status is **not** patchable — use action endpoints. | `200` — `InstanceOut` |
| `DELETE` | `/api/v1/instances/{instance_id}` | Soft-delete. Fails with `409` if status is `running` (must stop first). Idempotent if already `deleting`. | `204` |

### Action Endpoints (Stripe-style)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/instances/{instance_id}/deploy` | `creating` / `restarting` -> `deploying` |
| `POST` | `/api/v1/instances/{instance_id}/start` | `pending` / `deploying` -> `running` |
| `POST` | `/api/v1/instances/{instance_id}/restart` | `running` / `failed` -> `restarting` |
| `POST` | `/api/v1/instances/{instance_id}/stop` | `running` -> `pending` |
| `POST` | `/api/v1/instances/{instance_id}/fail` | any -> `failed`. Body: `{"reason": "string"}` |

### Create Payload (`InstanceCreate`)

```json
{
  "employee_id": "uuid",
  "office_id": "uuid",
  "workspace_path": ".pi/workspace/alice-a1b2c3d4/",  // optional, auto-generated
  "runtime_config": {}                                  // optional, defaults to {}
}
```

### Concurrency Safety

All action endpoints acquire a row-level lock (`SELECT ... FOR UPDATE`) on the Instance row before validating the current status and applying the transition. This prevents concurrent actions from racing on the same Instance.

## 3. Instance Lifecycle Events

Each lifecycle transition emits an event via the P3.5 event system (`app.core.events.emit`). Events carry `actor_type="user"`, `resource_type="instance"`, and the Instance UUID as `resource_id`. Events are stored in the database and are available through the event query API.

| Event Type | Emitter | Payload |
|-----------|---------|---------|
| `instance.created` | `POST .../` create | `{workspace_path, office_id}` |
| `instance.deployed` | `POST .../deploy` | `{}` |
| `instance.started` | `POST .../start` | `{}` |
| `instance.restarted` | `POST .../restart` | `{}` |
| `instance.stopped` | `POST .../stop` | `{}` |
| `instance.failed` | `POST .../fail` | `{reason}` |
| `instance.deleted` | `DELETE ...` | `{previous_status}` |

> Event names follow the `<domain>.<action_past_tense>` convention (P7.5 refactor; previously `instance.deploying` / `instance.running` / `instance.restarting` used present participles). Event constants live in `app/core/event_types.py:INSTANCE_*`. All events carry `actor_type="user"`, `actor_id=<caller user_id>`, `resource_type="instance"`, `resource_id=<instance_id>`.

## 4. K8s Deployment Manifests

All manifests live under `eyot-artifacts/k8s/instance/`. Each file uses `{instance_id}` and `{office_id}` template variables that a deploy script substitutes before applying.

| File | Kind | Purpose |
|------|------|---------|
| `deployment.yaml` | Deployment | Single-replica pod running `eyot-instance:latest`. Mounts workspace PVC at `/data` (pi cwd), ConfigMap at `/etc/config` (SYSTEM.md bundle), optional workspace `shared` hostPath at `/data/shared`. Env from Secret. Resources: 100m CPU / 256Mi memory. |
| `configmap.yaml` | ConfigMap | Injects `RUNTIME_CONFIG` (JSON) and `INSTANCE_ID` into the container. |
| `pvc.yaml` | PersistentVolumeClaim | 1Gi `ReadWriteOnce` volume for the Instance workspace. One PVC per Instance. |
| `service.yaml` | Service | `ClusterIP` on port 8080. Internal-only communication. |
| `networkpolicy.yaml` | NetworkPolicy | Ingress isolation: only Pods with `office-id={office_id}` can connect. |
| `kustomization.yaml` | Kustomization | Groups all resources with common label `app: eyot-instance`. |

### Template Variable Reference

| Variable | Description | Used In |
|----------|-------------|---------|
| `{instance_id}` | Instance UUID | All manifests (name, labels, selectors, ConfigMap key, PVC name) |
| `{office_id}` | Workspace UUID | `deployment.yaml` labels, `networkpolicy.yaml` podSelector |

### Build and Deploy

```bash
# Build the instance image
docker build -t eyot-instance:latest -f eyot-artifacts/docker/Dockerfile.instance .

# Dry-run validation (no actual resources created)
kubectl apply --dry-run=server -k eyot-artifacts/k8s/instance/

# Apply (after substituting template variables)
kubectl apply -k eyot-artifacts/k8s/instance/

# Tear down
kubectl delete -k eyot-artifacts/k8s/instance/
```

## 5. Multi-Instance Isolation

Each Instance operates within its own namespace for workspace files, messages, and blackboard entries.

### Workspace Path

The workspace path follows the naming convention:

```
.pi/workspace/{entity_slug}-{instance_id[:8]}/
```

Generated by `app.core.workspace.generate_workspace_path()`. The function takes an entity slug and instance UUID, returning a unique directory path. If the caller provides a custom `workspace_path` during creation, that value is used instead (uniqueness is enforced at the database level by the `uq_instances_workspace_path` partial unique index).

### Filesystem Isolation (K8s)

In Kubernetes, each Instance Deployment references a dedicated PVC named `{instance_id}-workspace`. The PVC is `ReadWriteOnce`, so only the Instance Pod can mount it. No Instance can access another Instance's files.

### At the Database Level

- Each Instance is scoped to one Entity and one Workspace.
- Instance CRUD endpoints require the current user to hold `editor` or higher role in the Instance's Workspace (via the P6 permission system).
- Messages are routed to Instances by `instance_id` in the P5 messaging topology.
- Blackboard entries reference the Instance's `id` as the owner.

## 6. Langfuse Integration Plan

Langfuse is the planned observability backend for agent tracing in Eyot. P8's harness will initialize a Langfuse client per running Instance, using credentials stored in `Instance.runtime_config`.

### Reserved Fields in `runtime_config`

```json
{
  "langfuse_enabled": true,
  "langfuse_public_key": "pk-...",
  "langfuse_secret_key": "sk-...",
  "langfuse_host": "https://cloud.langfuse.com"
}
```

### P7 Status

- **No Langfuse SDK dependency** — `pyproject.toml` does not reference `langfuse`.
- **No initialization code** — the fields above are documentation-only placeholders in the Instance model's `runtime_config` docstring.
- **P8 responsibility** — the harness reads `runtime_config.langfuse_*` on Instance startup, initializes `Langfuse(trace_context=...)`, and wraps agent execution steps in Langfuse spans.

### Integration Point (P8 / superseded for chat path)

```
app.agent_runtime (legacy checkpoint loop; optional)
  └── reads Instance.runtime_config
       └── if langfuse_enabled:
            └── import langfuse
            └── Langfuse(public_key=..., secret_key=..., host=...)
            └── trace all LLM calls, tool invocations, and blackboard writes
```

## Tunnel + pi Host (PRD-v3.5)

Instance pods run **`eyot-instance-host`** (Node) as the main process:

1. Outbound WebSocket to Backend `WS /api/v1/tunnel/connect`
2. First frame `auth` with `instance_id` + `proxy_token` → `auth.ok`
3. Backend Composer `schedule_user_turn` sends `chat.request` when Host is connected
4. Host drives `pi --mode rpc` (JSONL stdin/stdout); maps `text_delta` → `chat.response.chunk`
5. Portal Composer continues to consume existing SSE (`/composer/.../stream`)

When Tunnel is offline, Backend keeps the in-process stub/LLM fallback (`tunnel.offline_fallback`).

`GET /api/v1/instances/{id}/tunnel-status` reports `{connected: bool}`.

Python `app.agent_runtime` is no longer the default container CMD.

### Schema Note

The `runtime_config` field is a `JSONB` column on the `instances` table. Its schema is validated by the Pydantic model at the API boundary but not enforced at the PostgreSQL level (no JSON Schema constraint). P8's harness should gracefully handle missing or malformed `langfuse_*` fields — default to disabled if the field is absent.

## Related Documents

- [API Architecture](api-architecture.md) — API conventions, error format, pagination
- [Messaging System](messaging-system.md) — Instance message routing (P5)
- [Blackboard System](blackboard-system.md) — Instance blackboard and workspace files (P6)
- [Observability](observability.md) — Event system and logging conventions
- [AGENTS.md](../AGENTS.md) — Development guide and commit conventions
