# Cocoa Harness System

The P8 Harness layer is Cocoa's D11 **control plane** — the active counterpart to P6's passive Blackboard. Where Blackboard stores collaboration state, the Harness decides when an Instance runs, when it stops, and how external commands reach it. This document covers the seven reference points that any contributor or downstream phase (P9 portal, P10 learning) must internalize before editing `app/core/harness_supervisor.py` or any sibling module.

## 1. D11 Control Plane Architecture

P11's D11 split places the harness in the role of a **process-local control registry** that bridges events, the database, and the running agent loop. The three parties are the Supervisor (in-memory state), the Instance (DB row + agent process), and the Event System (P3.5 dispatcher). The supervisor never writes business tables itself; it observes events and emits downstream control events.

```
                 +-------------------------------+
                 |       Event System (P3.5)     |
                 |   in-process dispatcher + DB  |
                 +---------------+---------------+
                                 |
        emits harness.*          |          consumes control_sent
        observes via harness.*    |
                                 v
+-----------------+    in-memory      +---------------------+
|   Supervisor    | <---------->-----> |  Instance (DB row   |
| _registry: dict |  direct calls      |   + agent process)  |
|  metrics +      |                    |                     |
|  breakers       |                    |  InstanceLoopState  |
+-----------------+                    |  (1:1 per instance) |
        |                              +----------+----------+
        |                                         |
        |  reads breaker config                    |  reads / writes
        |  on each checkpoint                      |  loop_status
        |                                         |
        +----------------->+----------------------+
                            |
                            v
                     +-------------+
                     | PostgreSQL  |
                     |  instance_  |
                     |  loop_states|
                     +-------------+
```

**Three-party contract**:

- The Supervisor's only persistent side effect is ``HARNESS_BREAKER_TRIPPED`` -> ``HARNESS_LOOP_STOPPED`` -> ``HARNESS_CONTROL_SENT(action=kill)``, emitted through the same short-lived session that ``_trip_breaker`` opens.
- The Instance is the source of ``HARNESS_LOOP_STARTED`` / ``HARNESS_CHECKPOINT`` / ``HARNESS_LOOP_STOPPED``; the runtime writes to its own ``InstanceLoopState`` row through its own sessions.
- Direct mutators (``handle_interrupt`` / ``handle_pause`` / ``handle_resume`` / ``capture_snapshot``) live on the Supervisor instance and are called by API endpoints; they update ``InstanceLoopState`` and emit corresponding events in the **caller's** session so the endpoint commits atomically.

## 2. Boulder Loop Engine

The Boulder loop is a checkpoint-pinned cycle: the agent emits a checkpoint, the supervisor records it, the agent may be killed by a breaker, and the next iteration may be a continuation that recovers from the last snapshot. P8 implements the engine without an LLM — see ``app/agent_runtime.py`` for the skeleton that emits ``HARNESS_LOOP_STARTED`` -> checkpoints -> ``HARNESS_LOOP_STOPPED`` and self-terminates on ``HARNESS_CONTROL_SENT(action=kill)``.

### Checkpoint Round-Trip

```
+-------+    POST /instances/{id}/start   +---------+   loop_started   +-----------------+
| Idle  | ------------------------------> | Running | --------------> | emit checkpoint |
+-------+                                 +---------+                 +--------+--------+
                                                ^                              |
                                                |                              | handlers fire
                                                |                              v
                                       handle_resume()                  _handle_checkpoint
                                       (direct mutator)                updates _registry
                                                                              |
                                                                              v
                                                                        _check_breakers
```

Each ``HARNESS_CHECKPOINT`` payload carries:

```python
{
    "token_estimate": int,
    "snapshot": {
        "plan_slug": "<InstanceLoopState.current_plan_ref>",
        "iteration": int,
        "todos": [...]  # validated by app.core.todo_enforcer
    }
}
```

### Continuation Injection Lifecycle

The supervisor never calls the agent back directly. Idle detection is delegated to ``app/core/continuation.py::idle_check_handler``, a periodic TaskQueue task that runs every 30 seconds. When ``state.last_checkpoint_at`` is older than ``state.idle_timeout_seconds`` AND no breaker has tripped, the handler emits ``HARNESS_CONTINUATION_INJECTED`` and the loop resets ``metrics.last_checkpoint_at = now``.

```python
# Continuation flow (skip-emit semantics)
state = await session.scalar(select(InstanceLoopState).where(instance_id == ...))
reason = await supervisor._check_breakers(state.instance_id, session)
if reason is None and (now - state.last_checkpoint_at) > state.idle_timeout_seconds:
    await emit(HARNESS_CONTINUATION_INJECTED, payload={
        "instance_id": state.instance_id,
        "plan_ref": state.current_plan_ref,
        "idle_seconds": ...
    })
```

### D6 Note-then-Clear Discipline

> **D6 Note-then-Clear Discipline**: The Boulder loop enforces D6 by writing key context to notepad BEFORE emitting each checkpoint, then clears the in-context window. On continuation, the agent recovers from `boulder_snapshot` + notepad append-log. This is the implementation of the "note then clear" context discipline that P8 inherits from oh-my-openagent.

The plan defines the canonical wording as: **"上下文要点先落 notepad（note），checkpoint 落库后上下文即可清空（clear），continuation 时从 `boulder_snapshot` + notepad 恢复"**. The mapping is exact:

- **Note phase**: ``app.agent_runtime.run_agent_loop`` calls ``append_to_notepad`` with ``plan_slug=p8-bootstrap`` and ``notepad_name="learnings"`` BEFORE emitting the checkpoint event.
- **Clear phase**: The checkpoint payload's ``snapshot`` is the only structured state persisted; the in-context window is the responsibility of the upstream LLM driver (P9+).
- **Recover phase**: ``_handle_continuation_injected`` resets the idle clock, and ``POST /instances/{id}/snapshot`` returns the last ``boulder_snapshot`` plus live ``continuation_count`` so the agent can re-read both ``boulder_snapshot`` and the notepad append-log.

## 3. Four Deterministic Circuit Breakers

The supervisor guards every running loop with four breakers. They are checked in a fixed order so the first to trip wins; subsequent breakers for the same checkpoint are skipped. All four read configuration from the same ``InstanceLoopState`` row, so changing one breaker (e.g. via operator UI in P9+) does not require restarting the loop.

| # | Breaker | Config Field | Trigger Condition | Source |
|---|---------|--------------|-------------------|--------|
| 1 | ``max_continuations`` | ``max_continuations`` (default 50) | ``metrics.continuation_count >= config`` | Counted per ``HARNESS_CHECKPOINT`` |
| 2 | ``token_budget`` | ``max_token_estimate`` (default 100000) | ``metrics.token_estimate >= config`` | Accumulated ``payload["token_estimate"]`` |
| 3 | ``wall_clock`` | ``max_wall_clock_seconds`` (default 3600) | ``now - metrics.wall_clock_started >= config`` | Started on ``HARNESS_LOOP_STARTED`` |
| 4 | ``idle_timeout`` | ``idle_timeout_seconds`` (default 300) | ``now - metrics.last_checkpoint_at >= config`` | Updated on checkpoint + continuation |

### Evaluation Order

The exact order in ``_check_breakers`` (see ``app/core/harness_supervisor.py``):

```python
if metrics.continuation_count >= config["max_continuations"]:
    await self._trip_breaker(instance_id, "max_continuations")
    return "max_continuations"
if metrics.token_estimate >= config["max_token_estimate"]:
    await self._trip_breaker(instance_id, "token_budget")
    return "token_budget"
now = datetime.now(timezone.utc)
if metrics.wall_clock_started is not None and \
   (now - metrics.wall_clock_started).total_seconds() >= config["max_wall_clock_seconds"]:
    await self._trip_breaker(instance_id, "wall_clock")
    return "wall_clock"
if metrics.last_checkpoint_at is not None and \
   (now - metrics.last_checkpoint_at).total_seconds() >= config["idle_timeout_seconds"]:
    await self._trip_breaker(instance_id, "idle_timeout")
    return "idle_timeout"
```

When a breaker trips, ``_trip_breaker`` emits three events in a single short-lived session: ``HARNESS_BREAKER_TRIPPED``, ``HARNESS_LOOP_STOPPED``, and ``HARNESS_CONTROL_SENT(action=kill)``. The session is committed before the in-memory registry entry is removed, so a commit failure preserves the registry entry and the next checkpoint will re-attempt the trip.

## 4. Control Command Reference

P8 adds five control-plane endpoints under ``/instances`` (mounted by P7's instances router). All five are direct mutators — they do not flow through the in-process dispatcher.

| Command | Endpoint | Slash Syntax | Handler |
|---------|----------|--------------|---------|
| interrupt | ``POST /api/v1/instances/{instance_id}/interrupt`` | ``/interrupt`` | ``supervisor.handle_interrupt`` |
| pause | ``POST /api/v1/instances/{instance_id}/pause`` | ``/pause`` | ``supervisor.handle_pause`` |
| resume | ``POST /api/v1/instances/{instance_id}/resume`` | ``/resume`` | ``supervisor.handle_resume`` |
| status | ``GET  /api/v1/instances/{instance_id}/status`` | ``/status`` | ``supervisor.get_loop_status`` (read) |
| snapshot | ``POST /api/v1/instances/{instance_id}/snapshot`` | ``/snapshot`` | ``supervisor.capture_snapshot`` |

### State Transition Table

Allowed transitions are enforced by ``_get_state_or_404`` + the in-row ``loop_status`` write. Each mutator updates ``loop_status`` and emits one event:

| Endpoint | loop_status Source | loop_status Target | Event Emitted |
|----------|--------------------|---------------------|----------------|
| ``POST .../interrupt`` | running, paused | interrupted | ``HARNESS_INTERRUPTED`` + ``HARNESS_CONTROL_SENT(action=kill)`` |
| ``POST .../pause`` | running | paused | ``HARNESS_PAUSED`` |
| ``POST .../resume`` | idle, paused | running | ``HARNESS_RESUMED`` |
| ``GET .../status`` | any (read) | unchanged | none |
| ``POST .../snapshot`` | any (read+validate) | unchanged | none |

The ``capture_snapshot`` mutator does NOT change ``loop_status``; it validates the current ``boulder_snapshot`` through ``app.core.todo_enforcer.validate_boulder_snapshot`` and returns ``(snapshot, continuation_count, captured_at)``. Validation failures map to ``TodoEnforcerError`` -> ``ValidationError`` -> HTTP 422 via the API envelope.

## 5. Notepad Contract

The notepad is the file-system append-log that the D6 note phase writes into. ``app/core/notepad.py`` is the only owner; the rest of the codebase calls ``append_to_notepad`` and ``read_notepad`` and never edits the file in place.

### Append-Only Guarantee

The module exposes three functions:

```python
async def ensure_notepad_dir(workspace_path: str, plan_slug: str) -> str: ...
async def append_to_notepad(
    workspace_path: str, plan_slug: str, notepad_name: str, entry: str
) -> str: ...
async def read_notepad(
    workspace_path: str, plan_slug: str, notepad_name: str
) -> str: ...
```

There is no edit or delete operation. Each ``append_to_notepad`` call writes a single timestamped line:

```
[<ISO-8601-UTC-timestamp>] <entry>
```

### Four Standard Notepad Files

The constant ``VALID_NOTEPADS = ["learnings", "issues", "decisions", "problems"]`` is the canonical list; any call with an unknown name raises ``ValueError``. Each notepad file lives at:

```
<workspace_path>/.omo/notepads/<plan_slug>/<notepad_name>.md
```

``ensure_notepad_dir`` creates the directory tree with ``os.makedirs(..., exist_ok=True)``, so callers may invoke it on every append without tracking directory state.

### workspace_path Resolution

The agent runtime resolves the workspace path through ``_resolve_workspace_path``:

1. Read ``Instance.workspace_path`` from the DB (P7-generated ``.pi/workspace/<slug>-<id[:8]>/``).
2. If the row is missing or the column is ``NULL``, fall back to ``tempfile.mkdtemp(prefix=f"cocoa-agent-{instance_id}-")``.
3. Notepad writes go to that path's ``.omo/notepads/`` subtree.

This means the notepad lives on the Instance's PVC in production and on the local filesystem in dev — the API contract is identical.

## 6. Agent Runtime Skeleton

``app/agent_runtime.py`` implements a non-LLM loop that exercises the harness end-to-end so P8 unit tests (Todo 11) can assert the event flow without depending on a model. The skeleton has 10 iterations with a 0.2-second delay each, plus a per-loop ``HARNESS_CONTROL_SENT`` handler that flips a ``stop_flag`` on kill.

### Event Flow Timing

```
t=0    register HARNESS_CONTROL_SENT kill handler
       |
       v
t=0    emit HARNESS_LOOP_STARTED  -> supervisor._registry[i] = InstanceLoopMetrics(wall_clock=now)
       |
       v
t=0.2  iteration 0
       check stop_flag (False)                    # per-iteration check
       append_to_notepad("p8-bootstrap", "learnings", "Checkpoint 0")
       emit HARNESS_CHECKPOINT {token_estimate:0, snapshot:{...}}
                                                # supervisor._handle_checkpoint
                                                #   -> increment counters
                                                #   -> _check_breakers
       |
       v
t=0.4  iteration 1
       ... (10 iterations total)
       |
       v
t=2.0  emit HARNESS_LOOP_STOPPED
       -> supervisor._handle_loop_stopped: _registry.pop(i)
       deregister handler (note: register_handler appends only; leaving the
       handler in place is benign — it short-circuits when payload's
       instance_id no longer matches)
```

The kill path is split:

- **Control downlink kill** (``HARNESS_CONTROL_SENT(action=kill)``): the per-loop handler flips ``stop_flag`` -> checked at the top of every iteration -> loop breaks -> ``HARNESS_LOOP_STOPPED`` is emitted on the way out.
- **DB status kill** (``InstanceLoopState.loop_status in {interrupted, paused}``): the loop also reads the row each iteration and self-terminates if the status no longer says running. This is the safety net for cases where the kill event was missed.

## 7. Control Downlink Dual Paths

The agent runtime reacts to control commands through TWO independent paths. The supervisor emits BOTH paths and the runtime BOTH checks; whichever lands first wins.

| Path | Trigger | Delivery | Latency | Failure Mode |
|------|---------|----------|---------|--------------|
| Event path | ``HARNESS_CONTROL_SENT`` via ``emit()`` -> dispatcher -> ``register_handler`` callback | In-process (zero network) | Sub-millisecond | If handler missed (e.g. GC delay), loop continues until next check |
| DB path | ``InstanceLoopState.loop_status`` row write | Through SQLAlchemy session | One read-tx per iteration (~200ms) | Always wins on next iteration even if event lost |

### When Each Wins

- **Event wins on the fast path**: an interrupt issued via ``POST .../interrupt`` emits ``HARNESS_CONTROL_SENT(action=kill)`` in the same endpoint transaction. The runtime's ``stop_flag`` flips within milliseconds; the next iteration breaks before doing work.
- **DB wins on the safe path**: a breaker trip mutates ``loop_status`` only indirectly — the trip emits ``HARNESS_CONTROL_SENT`` but does not write to the DB row (the registry pop is in-memory). The runtime's DB read sees ``loop_status=running`` until something else (P9 portal) flips it; if that never happens, the ``idle_timeout`` breaker will catch the now-stale checkpoint at the next ``HARNESS_CHECKPOINT``.

The two paths are deliberately redundant: the event path is fast (millisecond latency) but can be lost to GC or process restart; the DB path is slower (one iteration tick) but always wins on the next read. The supervisor's ``shutdown()`` method cancels any active runtime ``asyncio.Task`` directly via the registry, ensuring even an event-loop-level GC pause cannot strand a loop during process shutdown.

## Related Documents

- [API Architecture](api-architecture.md) — REST conventions, error envelope, action endpoints
- [Runtime System](runtime-system.md) — Instance lifecycle, K8s scaffolding, workspace paths
- [Messaging System](messaging-system.md) — Activation triggers feeding the harness
- [Blackboard System](blackboard-system.md) — Passive state the harness writes to
- [Observability](observability.md) — Event constants and dispatcher semantics
- [AGENTS.md](../AGENTS.md) — Development guide and commit conventions
