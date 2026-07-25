# Messaging System

> Message topology, neighbor-only delivery, activation triggers, and directive
> routing for Cocoa P5. Covers the messaging API, corridor-gated message flow,
> and the intern hot-load lifecycle.

---

## 1. Topology Model

The messaging topology models an **acyclic directed graph** over memberships
within an office. Each membership is a node; each corridor is a directed edge
between two nodes.

```
Office
  |
  +-- Membership A (user or instance in office, role + hex position)
  |     |   role: owner | member | observer
  |     |   hex_q, hex_r: hexagonal grid coordinates
  |
  +-- Membership B
  |     |
  |     +-- Corridor from A -> B (one-way edge, is_active toggle)
  |
  +-- Membership C
        |
        +-- Corridor from A -> C

Message routing: only direct neighbors (A -> B, A -> C) receive delivery.
A cannot reach C through B (no transitive routing). The graph is enforced
acyclic at corridor creation via BFS (`app/core/topology.py:check_acyclic`).
```

**Key rules:**

- **Neighbor-only delivery**: A message from member X only reaches members Y
  where a Corridor `from_membership_id=X, to_membership_id=Y` is active.
- **Corridor gating**: Even if both memberships exist in the same office, a
  missing or inactive corridor blocks delivery (reason: `not_neighbor`).
- **Membership role model**: Three roles (`owner`, `member`, `observer`)
  defined in `app/models/office.py:MembershipRole`. Role does not affect
  delivery routing — it is metadata for authorization logic (P8+).
- **Acyclicity**: `check_acyclic` runs a BFS from the target membership to
  detect if the source is already reachable. If so, the new edge is rejected
  with a 409 Conflict to prevent cycles.

**Models (in `app/models/office.py`):**

```python
class Membership(BaseModel):
    office_id: str
    user_id: str | None
    instance_id: str | None
    hex_q: int          # column position in hex grid
    hex_r: int          # row position in hex grid
    role: MembershipRole  # owner | member | observer

class Corridor(BaseModel):
    office_id: str
    from_membership_id: str   # FK -> membership.id
    to_membership_id: str     # FK -> membership.id
    is_active: bool            # toggle delivery without deleting
```

---

## 2. Membership & Corridor API Reference

All endpoints are mounted under `/api/v1/messaging` (prefix defined in
`app/api/v1/messaging.py:router`).

### Membership CRUD

| Method | Path | Description | Status |
|--------|------|-------------|--------|
| `GET` | `/api/v1/messaging/memberships` | List memberships (offset pagination, `?office_id=` required) | 200 |
| `GET` | `/api/v1/messaging/memberships/{id}` | Get membership by ID | 200 / 404 |
| `POST` | `/api/v1/messaging/memberships` | Create membership (or reactivate soft-deleted) | 201 / 409 |
| `PATCH` | `/api/v1/messaging/memberships/{id}` | Partial update membership fields | 200 / 404 |
| `DELETE` | `/api/v1/messaging/memberships/{id}` | Soft-delete membership (last-owner check) | 204 / 404 / 409 |

### Corridor CRUD

| Method | Path | Description | Status |
|--------|------|-------------|--------|
| `GET` | `/api/v1/messaging/corridors` | List corridors (offset pagination, `?office_id=` required) | 200 |
| `GET` | `/api/v1/messaging/corridors/{id}` | Get corridor by ID | 200 / 404 |
| `POST` | `/api/v1/messaging/corridors` | Create corridor (acyclicity check, or reactivate) | 201 / 409 |
| `PATCH` | `/api/v1/messaging/corridors/{id}` | Partial update corridor fields | 200 / 404 |
| `DELETE` | `/api/v1/messaging/corridors/{id}` | Soft-delete corridor | 204 / 404 |

### Message Sending

| Method | Path | Description | Status |
|--------|------|-------------|--------|
| `POST` | `/api/v1/messaging/messages` | Send a turn (parse + route per directive) | 200 |

### Scaffold (501 — deferred to later phase)

| Method | Path | Description | Status |
|--------|------|-------------|--------|
| `POST` | `/api/v1/messaging/meetings` | Create a meeting | 501 |
| `POST` | `/api/v1/messaging/scheduled-tasks` | Create a scheduled task | 501 |

---

## 3. Message Delivery Flow

Messages follow a **fire-and-forget** path: no message is persisted to the
database. Only audit events are recorded.

```
User input
  |
  v
parse_turn()                -- app/core/slash_parser.py
  |  raw_text -> Turn (list[Directive] + general_text)
  v
route_turn()                -- app/core/directive_router.py
  |  For each directive:
  |    1. Resolve sender Membership in office
  |    2. If target is intern, hot-load instance
  |    3. route_message() per directive
  |    4. On success, trigger_on_mention()
  v
route_message()             -- app/core/message_router.py
  |  For each target:
  |    a. Find Employee by slug
  |    b. Find active Instance(s) (running | pending)
  |    c. Find target Membership (by instance_id + office_id)
  |    d. Check Corridor (from -> to, active, not deleted)
  |       - Missing -> emit "messaging.delivery_blocked", reason: not_neighbor
  |       - Found   -> emit "messaging.message_sent", delivered: true
  v
Audit events only (no message rows)
```

### Audit Event Types

Defined in `app/core/event_types.py`:

```python
MESSAGING_MESSAGE_SENT       = "messaging.message_sent"
MESSAGING_DELIVERY_BLOCKED   = "messaging.delivery_blocked"
MESSAGING_ACTIVATION_TRIGGERED = "messaging.activation_triggered"
```

| Event | Emitted When | Trigger Location |
|-------|-------------|------------------|
| `message_sent` | Corridor exists, delivery allowed | `route_message()` line 133 |
| `delivery_blocked` | No active corridor between members | `route_message()` line 115 |
| `activation_triggered` | on_mention or daily_report fires | `trigger_on_mention()` / `_daily_report_handler()` |

---

## 4. Activation Triggers

Three trigger types defined in `app/core/activation.py`.

| Trigger | Fires | Mechanism | Handler |
|---------|-------|-----------|---------|
| `daily_report` | Once per 24h (first run after 5s) | TaskQueue recurring task | `_daily_report_handler()` |
| `on_mention` | After successful message delivery | Called by `route_turn()` | `trigger_on_mention()` |
| `intern_hot_load` | When a directive targets an intern | Called by `route_turn()` | `handle_intern_invocation()` |

### Event Payload Format

All activation events share the same event type and payload shape:

```python
await emit(
    MESSAGING_ACTIVATION_TRIGGERED,  # "messaging.activation_triggered"
    actor_type="system" | "user",
    resource_type="employee" | "instance",
    resource_id=target_id,
    payload={
        "trigger": "daily_report" | "on_mention",
        "office_id": office_id,
        # optional extra fields per trigger type
    },
    session=session,
)
```

P5 only records the event. The P8 harness consumes these events for real sync
logic (e.g. daily report generation, on-mention response workflows).

### Daily Report Scheduling

```python
# app/core/activation.py:schedule_daily_report_sync()
# Called once in lifespan after TaskQueue is ready
task_queue.register_task("daily_report_sync", _daily_report_handler)
task_queue.enqueue("daily_report_sync", delay=5.0)  # first run +5s

# Handler iterates all offices, finds employees, emits events,
# then re-enqueues for 86400s (24h).
```

---

## 5. Directive Routing

The full routing chain from raw user input to per-instance delivery:

```
POST /api/v1/messaging/messages
{ "turn_text": "@ling-shi /analyze:PR-42", "office_id": "..." }
  |
  v
parse_turn(turn_text)                       # app/core/slash_parser.py:97
  |  Returns Turn(directives=[Directive(...)], general_text=None)
  |  Directive fields: target_employee, cmd, args, content_ref, raw_text
  v
route_turn(session, raw_text, office_id, from_user_id)  # app/core/directive_router.py:27
  |  1. Find sender's Membership by user_id + office_id
  |  2. For each directive:
  |     a. Check if target_employee has intern rank -> handle_intern_invocation()
  |     b. route_message(session, sender_membership_id, office_id, directive)
  |     c. If delivered -> trigger_on_mention(session, employee_id, office_id)
  v
route_message(session, from_membership_id, office_id, directive)  # app/core/message_router.py:29
  |  For each active Instance of the target employee in this office:
  |    1. Find Employee by slug
  |    2. Find Instance(s) (running | pending)
  |    3. Find target Membership (by instance_id)
  |    4. Check Corridor (from -> to, active)
  |       - route blocked if no corridor (reason: "not_neighbor")
  |       - route allowed -> emit MESSAGING_MESSAGE_SENT, delivered=true
  v
Returns list[MessageDeliveryResult]:
  MessageDeliveryResult(target_employee, delivered, reason, instance_id)
```

### Directive Input Grammar (P4 slash-protocol)

```ebnf
<turn>       := <directive>+
<directive>  := [<target>] <cmd> [<args>] [<content-ref>]
<target>     := "@" <employee-name>
<cmd>        := "/" <name>
<content-ref> : "@" <scope> [":" <path>]
scope        := "workspace" | "blackboard" | "vault" | "memory"
```

Parsed by `parse_directive()` in `app/core/slash_parser.py:42`.

---

## 6. Intern Hot-Load Semantics

Intern-rank employees (`EmployeeRank.intern`) have special invocation behavior
defined in `app/core/activation.py:handle_intern_invocation()`.

**Characteristics:**

| Property | Behavior |
|----------|----------|
| State | Stateless — no memory read/write |
| Instance | Temporary, created on first invocation |
| Instance reuse | If a running Instance already exists, reuse it |
| Instance path | `.pi/workspace/{slug}-{random8}` |
| Initial status | `creating` (P8 harness transitions to `running`) |
| Cleanup | Ephemeral — no explicit teardown in P5 |

**Flow:**

```python
async def handle_intern_invocation(session, employee_slug, office_id):
    # 1. Find Employee by slug, must be rank=intern
    employee = (select Employee where slug==employee_slug, rank==intern, not deleted)

    # 2. Check for existing running Instance
    existing = (select Instance where employee_id==..., office_id==..., status==running)

    # 3. Reuse or create
    if existing: return existing
    return Instance(employee_id, office_id, status=creating, workspace_path=...)
```

This function is called by `route_turn()` before routing each directive that
targets an intern. If the employee is not intern-rank, this function returns
`None` (no Instance is created).

---

## 7. Deferred

### Meeting & Scheduled-Task Scaffold

Two endpoints return HTTP 501 (`not_implemented`) as placeholders:

```python
# cocoa-backend/app/api/v1/messaging.py

@router.post("/meetings", status_code=501)
async def create_meeting():
    return {
        "error_code": "not_implemented",
        "message_key": "errors.not_implemented",
        "message": "Meeting semantics deferred to later phase",
    }

@router.post("/scheduled-tasks", status_code=501)
async def create_scheduled_task():
    return {
        "error_code": "not_implemented",
        "message_key": "errors.not_implemented",
        "message": "Scheduled-task semantics deferred to later phase",
    }
```

These will be implemented in a later phase with full CRUD, recurrence, and
corridor-gated participation semantics.

### Rings & Cycles

The topology is currently acyclic-only. Support for cyclic topologies
("rings", where A -> B and B -> A forms a 2-node cycle) is deferred to a
later phase. The `check_acyclic` BFS will need to accept configurable cycle
depth or be replaced with a ring-aware validator.

No `rings` or `cycles` endpoints exist in P5.
