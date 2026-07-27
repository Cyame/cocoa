# Cocoa Portal System

The P9 Portal is Cocoa's operator console — a React 19 single-page application that visualizes the backend control plane (P3.5 event stream, P5 message topology, P8 Harness Supervisor, P4 preset registry, Membership coordinates, CorridorNode canvas elements, and glow-mapped loop-status states). This document covers the architecture, page inventory, backend API surface, and visualization algorithms that any contributor or downstream phase (P9.5 polish, P10 learning) must internalize before editing the portal or its data contracts.

## 1. Portal Architecture

The portal is a client-side React application with zero additional npm dependencies beyond the P1.5 scaffold. All visual rendering uses pure SVG, Tailwind CSS v4, and lucide-react icons — no React Flow, D3, or cytoscape.

```
+---------------------------------------------------+
|                   Cocoa Portal                     |
|  React 19 + Vite 8 + TypeScript + Tailwind v4     |
+---------------------------------------------------+
|  Pages (7)       |  Components (4)  |  Stores (2) |
|  ComposerPage    |  AppShell        |  session.ts |
|  DebugPage       |  TopologyToolbar |  selected.ts|
|  InstanceDetail  |  TopologyGlow    |             |
|  LoginPage       |  CommandAuto-    |             |
|  OfficeDetail    |  complete        |             |
|  OfficeList      |                  |             |
|  TopologyPage    |                  |             |
+------------------+------------------+-------------+
|  lib/api.ts      |  lib/types.ts    |  lib/slash- |
|  fetch wrapper   |  backend schema  |  parser.ts  |
|  + ApiError      |  mirror          |  TS mirror  |
+------------------+------------------+-------------+
                          |
                    Vite proxy /api -> backend:4510
                          |
              +-----------+-----------+
              |   FastAPI Backend     |
              |   /api/v1/*           |
              +-----------------------+
```

**Key architectural decisions:**

- **API client**: `src/lib/api.ts` — a typed `fetch` wrapper that injects `Authorization: Bearer <token>`, auto-redirects to `/login` on 401, and throws typed `ApiError`.
- **State management**: Zustand with `persist` middleware. `useSessionStore` holds JWT in localStorage. `useSelectedStore` holds `officeId`, `instanceId`, and `interactionMode` (persisted as `cocoa.topology.mode`).
- **Routing**: `react-router` v7 with `createBrowserRouter`. The root path `/` redirects to `/login` (unauthenticated) or `/offices` (authenticated). Six nested routes live under the `App` layout shell.
- **Topology rendering**: Pure SVG with `<svg viewBox>`, `<g transform="translate(pan_x, pan_y) scale(zoom)">`, and `<defs><filter>` for glow effects. Mouse wheel zoom + drag-to-pan via React state.
- **Live status polling**: `setInterval` at 2-second intervals on `GET /offices/{id}/live-status`. No WebSocket or SSE — debug-first simplicity.
- **Connection animation**: Polls `GET /events?type_prefix=messaging.&since=<5 seconds ago>` to detect message flow; renders SVG `<animateMotion>` particles on matching corridor `<line>` elements for 1 second.

## 2. Page Inventory

The portal has 7 route-level pages and 4 shared components. Each page maps to one or more backend endpoints.

### Route Table

| Path | Page Component | Purpose | Backend Endpoints Used |
|------|---------------|---------|------------------------|
| `/login` | `LoginPage` | Username/password authentication | `POST /auth/login` |
| `/offices` | `OfficeListPage` | Card grid of accessible offices | `GET /offices` |
| `/offices/:id` | `OfficeDetailPage` | Office tabs: Employees, Instances, Blackboard | `GET /messaging/memberships?office_id=`, `GET /instances`, `GET /blackboards` |
| `/offices/:id/instances/:iid` | `InstanceDetailPage` | Instance status bar + harness control buttons + event panel | `GET /instances/{id}/status`, `POST /instances/{id}/{interrupt,pause,resume,snapshot}`, `GET /events` |
| `/offices/:id/topology` | `TopologyPage` | Interactive SVG canvas: circle nodes with glow, corridor lines, pan/zoom, 3-mode toolbar | `GET /messaging/memberships`, `GET /messaging/corridors`, `GET /learning/corridor-nodes`, `GET /offices/{id}/live-status`, `GET /events`, `PATCH /messaging/memberships/{id}`, `PATCH /learning/corridor-nodes/{id}`, `POST /messaging/corridors` |
| `/offices/:id/composer` | `ComposerPage` | Multi-`@` compartmentalized message editor + slash command autocomplete | `POST /messaging/messages`, `GET /employee-presets/{slug}` |
| `/debug` | `DebugPage` | Full-width event table with filter bar, polling, and JSON export | `GET /events` |

### Component Inventory

| Component | File | Purpose |
|-----------|------|---------|
| `AppShell` | `src/components/AppShell.tsx` | Layout wrapper: left navigation (Office list / Debug / Composer / Topology links) + top bar (user info + logout) |
| `TopologyToolbar` | `src/components/TopologyToolbar.tsx` | Three-mode switch: Select (`<MousePointer />`) / Connect (`<Link />`) / Move (`<Move />`) with keyboard shortcuts `V`/`C`/`M` |
| `TopologyGlow` | `src/components/TopologyGlow.tsx` | SVG `<defs>` filter generator: produces `feGaussianBlur` + `feFlood` + `feComposite` filters per glow color at the correct intensity |
| `CommandAutocomplete` | `src/components/CommandAutocomplete.tsx` | Dropdown popup triggered by `/` in the composer: shows GLOBAL_COMMANDS + CONTROL_COMMANDS + per-preset manifest.commands, with keyboard navigation |

### Zustand Stores

| Store | File | Persisted Fields |
|-------|------|-----------------|
| `useSessionStore` | `src/stores/session.ts` | `token` (JWT string), `user` (CurrentUser object) — localStorage |
| `useSelectedStore` | `src/stores/selected.ts` | `officeId`, `instanceId`, `interactionMode` — only `interactionMode` persisted to localStorage as `cocoa.topology.mode` |

## 3. Event Query API

`GET /api/v1/events` serves as the audit-log backbone for three portal features: the Debug page's raw event table, the Instance detail page's per-instance event panel, and the Topology viz's corridor-animation detection.

### Endpoint Signature

```
GET /api/v1/events?type_prefix=&resource_type=&resource_id=&request_id=&since=&until=&limit=50&cursor=
```

All six filter parameters are optional and combined with SQL `AND`. The `type_prefix` parameter matches via SQL `LIKE 'prefix%'`; the other five are exact equality except `since`/`until` which are inclusive range bounds on `created_at`.

### Pagination

Results are ordered `(created_at DESC, id DESC)` — newest first. Cursor pagination uses a base64-encoded compound key `(created_at, id)` to handle timestamp collisions gracefully. The response shape is:

```typescript
{
  items: EventOut[],
  next_cursor: string | null
}
```

### EventOut Schema

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` (UUID) | Immutable event ID |
| `type` | `string` | Dot-delimited event type, e.g. `harness.checkpoint`, `messaging.message_sent` |
| `actor_type` | `string` | Source of the event: `user`, `instance`, `system` |
| `actor_id` | `string \| null` | UUID of the actor |
| `resource_type` | `string \| null` | Affected resource kind: `instance`, `corridor`, `message`, etc. |
| `resource_id` | `string \| null` | UUID of the affected resource |
| `payload` | `JsonObject` | Event-specific structured data |
| `request_id` | `string \| null` | Correlation ID for tracing |
| `created_at` | `string` (ISO 8601) | UTC event timestamp |

The events table is append-only (P3.5 contract). No `deleted_at` filter is applied — every event persists forever. No `POST`/`PATCH`/`DELETE` is offered on this endpoint.

## 4. Live-Status API

`GET /api/v1/offices/{office_id}/live-status` provides the per-node glow state that the Topology viz polls at 2-second intervals. The endpoint aggregates all active memberships in the office and joins each against the `instance_loop_states` table to derive a glow color and intensity.

### Endpoint Signature

```
GET /api/v1/offices/{office_id}/live-status
Authorization: Bearer <token>
→ 200: LiveStatusItemOut[]
```

Permission: `require_office_role(..., "viewer")` — any office member can read.

### LiveStatusItemOut Schema

```typescript
{
  membership_id: string;       // Membership UUID
  posx: number;                // X coordinate on the canvas
  posy: number;                // Y coordinate on the canvas
  node_type: "user" | "instance";  // Determines glow logic branch
  glow: {
    color: string;             // Hex color like "#10b981"
    intensity: "static" | "weak" | "low" | "medium" | "strong";
  };
}
```

### Glow Derivation Logic

For **user memberships** (`node_type: "user"`): fixed glow `#4f46e5` (indigo) at `medium` intensity — human operators always look the same.

For **instance memberships** (`node_type: "instance"`): the `InstanceLoopState.loop_status` determines the glow via a discrete 6-way mapping:

| loop_status | Color | Intensity | Meaning |
|-------------|-------|-----------|---------|
| `running` | `#10b981` (green) | `strong` | Agent is actively executing a Boulder loop iteration |
| `idle` | `#eab308` (yellow) | `medium` | Agent is waiting for continuation or input |
| `paused` | `#94a3b8` (slate) | `weak` | Agent has been paused by an operator control command |
| `interrupted` | `#ef4444` (red) | `medium` | Agent was interrupted; breaker may have tripped |
| `completed` | `#3b82f6` (blue) | `low` | Agent finished its work without error |
| `failed` | `#dc2626` (red) | `strong` | Agent encountered an unrecoverable error |
| *(unknown)* | `#94a3b8` (slate) | `weak` | Fallback for unexpected status values |
| *(no loop state)* | `#94a3b8` (slate) | `static` | Instance exists but has never started a Boulder loop |

The mapping lives in `app/core/glow.py` as a `dict[str, GlowColor]` lookup. The `GlowIntensity` enum has 5 levels (`static`/`weak`/`low`/`medium`/`strong`), each mapped to an SVG filter `flood-opacity` in the `TopologyGlow` component.

## 5. CorridorNode API

CorridorNodes are first-class canvas elements introduced in P9 Todo 8 — named, positioned anchors that corridors can attach to. They are **not** office members (no user/instance FK, no role); they exist solely as structural topology nodes, analogous to nodeskclaw's `CorridorHex`.

### Model

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` (UUID) | Primary key |
| `office_id` | `string` (UUID FK) | Owning office |
| `posx` | `int` | X canvas coordinate |
| `posy` | `int` | Y canvas coordinate |
| `display_name` | `string` (64) | Human-readable label on the canvas |
| `glow_color` | `string \| null` (7) | Optional hex color override (the topology viz applies its own glow; this is the node's base identity color) |
| `status` | `"active" \| "paused" \| "archived"` | Lifecycle state |
| `created_by` | `string \| null` (UUID FK) | User who created the node |

Unique constraint: `uq_corridor_nodes_office_pos` — `(office_id, posx, posy)` unique among active rows (`deleted_at IS NULL`), preventing two nodes from sharing a canvas cell.

### CRUD Endpoints

All endpoints live under `/api/v1/learning/corridor-nodes` (shares the `/learning` namespace with P10; may be refactored to `/topology` in P9.5).

| Method | Path | Permission | Response |
|--------|------|-----------|----------|
| `GET` | `/learning/corridor-nodes?office_id=&limit=&cursor=` | `viewer` | `CorridorNodeListOut { items, next_cursor, total }` |
| `GET` | `/learning/corridor-nodes/{id}` | `viewer` | `CorridorNodeOut` |
| `POST` | `/learning/corridor-nodes` | `editor` | `201 CorridorNodeOut` |
| `PATCH` | `/learning/corridor-nodes/{id}` | `editor` | `CorridorNodeOut` |
| `DELETE` | `/learning/corridor-nodes/{id}` | `editor` | `204 No Content` |

- **POST body**: `{ office_id, posx, posy, display_name, glow_color?, status? }`
- **PATCH body**: Partial update — only provided fields are changed.
- **409 Conflict**: When creating or moving a node to an occupied `(office_id, posx, posy)` cell — surfaced via the partial unique index's `IntegrityError`.
- **Soft delete**: `DELETE` sets `deleted_at` on the row. Corridors that reference a deleted node keep their FK pointers valid (Postgres does not reject soft-deleted FK targets).

### Corridor Polymorphic Connection

P9 extends the existing P5 `Corridor` model to accept **three edge shapes**:

- **M <-> M**: Both endpoints are `Membership` records (original P5 design).
- **M <-> CN**: One endpoint is a `Membership`, the other is a `CorridorNode`.
- **CN <-> CN**: Both endpoints are `CorridorNode` records.

The `corridors` table has been altered with two CHECK constraints:

```sql
-- from side: exactly one of from_membership_id / from_corridor_node_id is non-null
CHECK ((from_membership_id IS NOT NULL)::int + (from_corridor_node_id IS NOT NULL)::int = 1)

-- to side: same constraint
CHECK ((to_membership_id IS NOT NULL)::int + (to_corridor_node_id IS NOT NULL)::int = 1)
```

The P5 acyclicity check (BFS on the membership graph) skips `CorridorNode` endpoints — they are not principals and do not participate in message routing. CorridorNodes that include such edges therefore do not affect message delivery semantics; they exist purely for visual grouping on the topology canvas.

## 6. Composer Compartmentalization Semantics

The Composer page (`/offices/:id/composer`) implements Cocoa's multi-recipient messaging model: a single text area that the operator types into, with real-time compartmentalization driven by `@{slug}` mentions.

### Compartmentalization Algorithm

The TypeScript parser (`src/lib/slash-parser.ts`) mirrors the P4 Python parser (`app/core/slash_parser.py::parse_turn()`) exactly. When the operator types:

```
@密士 /plan @workspace:foo.md
```

The parser produces:

1. **General text compartment**: everything before the first `@{slug}`.
2. **Per-recipient compartments**: each `@{slug}` opens a new compartment. The text following `@{slug}` up to the next `@{slug}` or end-of-input is assigned to that recipient.
3. **Directive extraction**: each compartment is scanned for `/{command}` directives and the general text is separated from commands.

### Slash Parser TypeScript Mirror

The mirror produces a `Turn { directives: Directive[], general_text: string }` structure identical to the Python backend. P9 tests include parity testing: `test_slash_parser_parity` in `tests/test_phase9_portal.py` validates that identical input strings produce byte-identical outputs across Python and TypeScript parsers.

### Command Autocomplete

The `CommandAutocomplete` component hooks into the `/{command}` parsing:

- Typing `/` opens a dropdown of available commands, categorized into:
  - **GLOBAL_COMMANDS**: `help`, `status`, `snapshot` — available to all compositions.
  - **CONTROL_COMMANDS**: `interrupt`, `pause`, `resume` — available when the target is an instance.
  - **PER-PRESET_COMMANDS**: fetched from `GET /employee-presets/{slug}` — the manifest's `commands` array for the current `@{slug}` target.
- Keyboard navigation: up/down arrows + Enter to select.
- Selected command is auto-inserted into the text area at cursor position.

The per-preset commands are cached in the session store after the first fetch for a given slug.

## 7. Topology Visualization Algorithm

The Topology page (`/offices/:id/topology`) is P9's flagship feature — an interactive SVG canvas that renders the office's agent topology as a graph of circular nodes with real-time glow status, connection lines between them, and three interaction modes.

### Coordinate System

The canvas uses SVG `viewBox="-1000 -1000 2000 2000"` with a `g` element transformed by `translate(pan_x, pan_y) scale(zoom)`. Node positions come directly from `Membership.posx/posy` and `CorridorNode.posx/posy` — the coordinates are free-form Cartesian pixels, not hex-grid cells. The origin `(0, 0)` is at canvas center.

### Node Rendering

Each node is rendered as an SVG group:

```svg
<g class="node" transform="translate(posx, posy)">
  <!-- Glow ring -->
  <circle r="44" fill="none"
          stroke="glow_color" stroke-width="6"
          stroke-opacity="intensity_value"
          filter="url(#glow-filter-{color})" />
  <!-- Inner disc -->
  <circle r="36" fill="agent_color" />
  <!-- Icon -->
  <foreignObject x="-12" y="-12" width="24" height="24">
    <Bot />  <!-- or <User /> for user memberships -->
  </foreignObject>
  <!-- Label -->
  <text y="54" text-anchor="middle" class="text-xs fill-slate-300">
    {display_name}
  </text>
</g>
```

### Glow Mapping

The glow ring's `stroke` and `stroke-opacity` come from `GET /offices/{id}/live-status` (Section 4). The SVG filter is generated by the `TopologyGlow` component using `<feGaussianBlur stdDeviation="6"/>` + `<feFlood flood-color="{color}" flood-opacity="{intensity}"/>` + `<feComposite/>`. The five intensity levels translate to:

| Intensity | `flood-opacity` | Visual |
|-----------|----------------|--------|
| `static` | 0.0 | No glow |
| `weak` | 0.15 | Faint halo |
| `low` | 0.25 | Subtle glow |
| `medium` | 0.45 | Visible glow |
| `strong` | 0.70 | Bright pulsing aura |

### Connection Lines

Corridor edges are rendered as `<line>` elements from the source node's `(posx, posy)` to the target node's `(posx, posy)`. Default stroke is `#94a3b8` (slate-400) at `stroke-width="2"`. Lines are completely static in the absence of message traffic.

### Connection Animation (Streaming)

The Topology page polls `GET /events?type_prefix=messaging.&since=<5 seconds ago ISO>` every 2 seconds. When an event matching a corridor is found (by `resource_type=corridor` + `resource_id=<corridor.id>`), the corresponding `<line>` is temporarily restyled:

1. The line's stroke changes to `#10b981` (green) at `stroke-width="3"` with `stroke-dasharray="4 2"`.
2. An SVG `<circle r="4" fill="#10b981">` particle is added with `<animateMotion path="M x1 y1 L x2 y2" dur="1s" />`, tracing the corridor path.
3. After 1 second, both the styling and the particle are removed, returning the line to its default static appearance.

This gives operators a real-time visual indicator of which corridors are actively carrying messages, without the overhead of a persistent connection.

### Pan and Zoom

Mouse wheel events on the SVG adjust the `zoom` state (clamped to `[0.1, 3.0]`). Dragging the canvas background (not a node) adjusts `pan_x` and `pan_y`. Both are stored in React `useState` — no external gesture library needed.

### Interaction Modes

The `TopologyToolbar` component switches between three modes, persisted to `localStorage` under `cocoa.topology.mode`:

| Mode | Key | Behavior |
|------|-----|----------|
| **Select** | `V` | Click a node to open a right-side drawer showing node details (type, name, status, glow). Click the canvas background to deselect. |
| **Connect** | `C` | Click source node A (highlighted) → click target node B → `POST /messaging/corridors` is called (body supports polymorphic endpoints per Section 5). Click the canvas background to cancel the pending connection. |
| **Move** | `M` | Mouse-down on a node enters drag mode. `mousemove` updates local `posx/posy` with `requestAnimationFrame` throttling. `mouseup` calls `PATCH /messaging/memberships/{id}` or `PATCH /learning/corridor-nodes/{id}` to persist. On 409 (position conflict), a toast displays the error and the node snaps back to its original position. |

## 8. P9.5 Follow-ups

The following items are deferred to P9.5 (polish wave). Nothing in P9 blocks them, but they are not yet implemented:

- **Memory viewer**: A dedicated page or panel to browse `MemoryEntry` records (P6) — currently accessible only via API.
- **Drag-to-reassign**: Drag an instance node from one `Membership` to another to reassign its office role — the composer only displays compartments, it does not mutate memberships.
- **SSE real-time channel**: Replace the 2-second polling loops with a Server-Sent Events endpoint for live-status and event streaming.
- **3D mode**: Alternative rendering of the topology canvas using Three.js or WebGL for spatial depth — P9 is purely 2D SVG.
- **Corridor reroute algorithm**: Allow operators to visually rewire corridors by dragging endpoints, with automatic `PATCH` to the corridor record.
- **Topology auto-layout**: Algorithmic node positioning (force-directed graph) as an alternative to manual drag placement.
- **/topology prefix refactor**: Move CorridorNode CRUD endpoints from `/learning/corridor-nodes` to a dedicated `/topology/corridor-nodes` prefix.

## Related Documents

- [Harness System](harness-system.md) — D11 control plane, Boulder loop engine, circuit breakers, control commands
- [Messaging System](messaging-system.md) — Message topology, neighbor-only delivery, corridor CRUD, directive routing
- [API Architecture](api-architecture.md) — REST conventions, error envelope, pagination, action endpoints
- [Runtime System](runtime-system.md) — Instance lifecycle model, K8s scaffolding
- [Preset System](preset-system.md) — EmployeePreset manifest schema, slash parser grammar
- [Blackboard System](blackboard-system.md) — Passive state, virtual filesystem, vault archiving
- [Observability](observability.md) — Event constants and dispatcher semantics
- [AGENTS.md](../AGENTS.md) — Development guide and commit conventions
