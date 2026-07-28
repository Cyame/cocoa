# Cocoa Learning System

> **Code rename pending (15d-rename wave)**: This document uses target (15d) naming — BaseClass, Entity, Workspace, Memory. The source code still uses legacy names (EmployeePreset, Employee, Office, MemoryEntry). API paths in this document reflect the current code; they will be renamed in the 15d-rename wave. See §7 for the full rename map.

The P10 Learning layer is Cocoa's skill-distillation subsystem — the bridge between accumulated entity memory and reusable base classes. It reads an Entity's Memory records, distills them into a structured `PresetManifest`, and creates a new BaseClass row. Two distinct actions drive this: **promote** (晋升, Instance → Entity) extracts a reusable Entity from a running Instance, and **transmute** (炼化, Entity → BaseClass) derives a BaseClass template from an Entity's accumulated memory. This document covers the architecture, Protocol interface, default algorithm, command integration, API reference, and future directions.

## 1. Learning Subsystem Architecture

P10 sits at the intersection of three established subsystems: **Memory** (P6 append-only log), **BaseClass** (P4 manifest registry), and **Directive Routing** (P5 command dispatch). It does NOT modify any existing table — it only reads from Memory and writes new rows to BaseClass.

```
  Entity  ---(writes)---> Memory (append-only)
     |                          |
     |                    [Memory read]
     v                          v
  BaseClass  <--- AggregatingDistiller (heuristic engine)
  (new row)                |
                           | DistillationEngine Protocol
                           | (pluggable interface)
                           v
                      PresetManifest
                      (model / prompt / skills / tools / commands)
                           |
                           v
                    P4 PresetRegistry
                    (in-memory cache refreshed on write)
```

**Key design decisions:**

- **Zero schema migration** — P2's `memory_entries` table (append-only, no `updated_at`) and BaseClass's `manifest` JSONB already support the required data shape. No new tables or columns.
- **Two actions, not one create** — P10 splits the old monolithic "distill creates a preset" into two distinct verbs:
  - **Promote** (晋升): Instance → Entity. An Instance's runtime state (memory, behavior, configuration) is extracted into a reusable Entity row. Useful when a running agent has accumulated valuable behavior that should be templated.
  - **Transmute** (炼化): Entity → BaseClass. An Entity's accumulated Memory is distilled into a BaseClass template (manifest). This is the classic "learn from experience" path.
- **New base class, not mutation** — Transmute creates a new BaseClass row with slug `{source_preset_slug or 'base'}-skill-{target_skill_slug}`. The source BaseClass remains unchanged, enabling A/B testing and rollback.
- **Engine does not write DB** — `DistillationEngine.distill()` returns a pure `DistillResult` dataclass. API endpoints handle persistence, slug uniqueness checks, and event emission. This matches the P8 harness handler contract.
- **Explicit user trigger** — Both `/promote` and `/transmute` are only invoked by the operator (API or slash command). No scheduled/auto-distill in P10.

## 2. DistillationEngine Protocol Interface Contract

The core abstraction is `DistillationEngine`, a `typing.Protocol` defined in `app/core/distillation.py`. Any class conforming to this interface can be substituted at runtime:

```python
class DistillationEngine(Protocol):
    async def distill(
        self,
        entity_id: str,
        *,
        action: str,            # "promote" or "transmute"
        request: DistillRequest,
        session: AsyncSession,
    ) -> DistillResult:
        ...
```

**Contract rules:**

| Rule | Detail |
|------|--------|
| Input | `entity_id` (UUID), `action` (`"promote"` or `"transmute"`), `DistillRequest` (target slug + kind filter + source preset + optional `instance_id` for promote), `AsyncSession` |
| Output | `DistillResult` dataclass with `new_preset_slug`, `manifest_preview` (`SkillManifestPreview`), `aggregated_memory` (`AggregatedMemoryCount`), `source_entity_id`, `source_preset_slug` |
| No side effects | Must NOT commit, flush, or emit events — pure computation with read-only DB access |
| Error handling | Raise `DistillationError(code, message_key, message)` for recoverable failures (e.g., no memory entries) |
| Duck typing | The Protocol is structural; no `isinstance` check needed. Callers type-annotate with `DistillationEngine` for IDE/linter support |

**DistillRequest fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | `str` | Yes | `"promote"` (Instance → Entity) or `"transmute"` (Entity → BaseClass) |
| `target_skill_slug` | `str` | Yes | Kebab-case slug for the new skill (pattern `^[a-z][a-z0-9-]*$`) |
| `memory_kind_filter` | `list[str] \| None` | No | Which `MemoryKind` values to include. `None` = all four kinds. Only used for `transmute`. |
| `source_preset_slug` | `str \| None` | No | Source BaseClass to inherit `model` from; `None` = use `"tbd"` |
| `target_preset_name` | `str \| None` | No | Human-readable name; `None` = auto-generate `"Skill: {slug}"` |
| `instance_id` | `str \| None` | No | Required for `action="promote"` — the Instance whose runtime state to promote. Ignored for `transmute`. |

## 3. AggregatingDistiller Algorithm

`AggregatingDistiller` is the default heuristic engine — stateless, deterministic, and pure. No LLM calls. It supports both promote and transmute modes.

### Transmute path (Entity → BaseClass)

**Algorithm steps:**

1. **Look up Entity** by `entity_id`. Raise `DistillationError("entity.not_found", ...)` if missing.
2. **Validate action** — if `action` is `"promote"`, verify `instance_id` is provided and route to the promote path instead.
3. **Query Memory** rows for the entity (`deleted_at IS NULL`), optionally filtered by `memory_kind_filter`.
4. **Raise if empty** — `DistillationError("learning.no_memory", ...)` when no entries match.
5. **Aggregate counts** by `MemoryKind` (experience / lesson / decision / problem) into `AggregatedMemoryCount`.
6. **Extract commands** from `lesson` and `decision` entries: keys matching kebab-case pattern (`^[a-z][a-z0-9-]+$`) are deduplicated and collected (max 10).
7. **Generate prompt** from the longest lesson content (>= 50 characters), truncated to 200 characters + `"..."`. Falls back to `"TODO P8"` if no qualifying lesson exists.
8. **Extract skills** from all entry keys: split on `-`, take the first segment, deduplicate.
9. **Model**: inherit from `source_preset.manifest["model"]` if `source_preset_slug` is provided and exists, otherwise `"tbd"`.
10. **Tools**: always empty (`[]`) — cannot be inferred from memory.
11. **Slug**: `f"{source_preset_slug or 'base'}-skill-{target_skill_slug}"`.

### Promote path (Instance → Entity)

**Algorithm steps:**

1. **Look up Entity** — if `entity_id` is provided and non-empty, use the existing Entity as the promotion target; otherwise create a new Entity row.
2. **Look up Instance** by `instance_id`. Raise `DistillationError("instance.not_found", ...)` if missing.
3. **Extract runtime state** — read the Instance's current `boulder_snapshot`, `notepad` entries, and recent Memory records generated during this Instance's lifetime.
4. **Generate Entity attributes** — populate `name`, `description`, and configuration from the Instance's manifest and runtime state.
5. **Slug**: `f"promoted-{instance_id[:8]}"` or reuse existing entity slug if targeting an existing Entity.

Promote is a net-new P10 action (no prior "distill creates entity" equivalent). The heuristic is minimal in P10; a richer LLM-based promote is deferred to P11+.

**Tuning constants** (defined at module level):

| Constant | Value | Purpose |
|----------|-------|---------|
| `_MIN_PROMPT_CHARS` | 50 | Minimum lesson content length to use as prompt |
| `_MAX_PROMPT_CHARS` | 200 | Maximum prompt length before truncation |
| `_MAX_COMMANDS` | 10 | Maximum extracted commands |
| `_CMD_PATTERN` | `^[a-z][a-z0-9-]+$` | Kebab-case validation regex |

## 4. LEARNING_COMMANDS — 4th Command Family

P10 introduces the fourth command family, registered in `app/core/preset_registry.py`:

```python
LEARNING_COMMANDS: list[str] = ["/promote", "/transmute", "/consolidate", "/reflect"]
```

| Family | Commands | Registered P | Route Target | Requires @target |
|--------|----------|-------------|--------------|-----------------|
| GLOBAL | `/read`, `/list`, `/write`, `/archive` | P4 | Message corridor | No |
| PER-PRESET | Defined in `manifest.commands` | P4 | Message corridor | Yes |
| CONTROL | `/interrupt`, `/pause`, `/resume`, `/status`, `/snapshot` | P8 | Harness Supervisor | Yes |
| **LEARNING** | `/promote`, `/transmute`, `/consolidate`, `/reflect` | **P10** | **AggregatingDistiller** | **Yes** |

> **Code note**: The source code currently uses `/distill` as the command name. Renaming to `/transmute` and adding `/promote` are part of the 15d-rename wave.

**P5 Routing Priority** (in `directive_router.py::route_turn()`):

```
is_control_command(cmd)  →  _route_control_directive()
is_learning_command(cmd)  →  _route_learning_directive()
is_global_command(cmd)  →  message corridor
per-preset command  →  message corridor
```

Control takes precedence over learning. Both require explicit `@target` (bare commands are silently dropped, matching P5 semantics). Learning is checked before global/per-preset so that `/transmute` and `/promote` do not accidentally match a per-preset command of the same name.

In the P10 implementation, only `/distill` (→ `/transmute` in rename wave) has a functional handler (`_route_learning_directive` in `directive_router.py`). `/promote`, `/consolidate`, and `/reflect` are registered as valid command names but have no implementation yet — they are deferred to P11+.

## 5. Learning API Endpoints Reference

All endpoints are prefixed with `/api/v1/learning` and registered in `app/api/v1/router.py`.

> **Code note**: The API paths below use the current source code naming (`employees`, `employee_id`, `employee-presets`, `presets`). The 15d-rename wave will update path segments: `employees` → `entities`, `employee_id` → `entity_id`, `presets` → `base-classes`.

### GET `/memories/{employee_id}/summary`

| Aspect | Detail |
|--------|--------|
| Permission | `require_workspace_role(..., "viewer")` — entity must belong to a workspace |
| Query params | `kind: list[str]` (multi-value filter), `limit: int` (1-200, default 50) |
| Response | `MemorySummaryOut` — `aggregated_counts` (per-kind ints + total), `sample_lessons` (<=5 lesson snippets), `sample_keys_by_kind` (<=5 per kind) |
| Events | None (read-only) |

### POST `/employees/{employee_id}/distill`

| Aspect | Detail |
|--------|--------|
| Permission | `require_workspace_role(..., "editor")` |
| Request body | `DistillRequest` — `action` (required: `"promote"` or `"transmute"`), `target_skill_slug` (required), `memory_kind_filter`, `source_preset_slug`, `target_preset_name`, `instance_id` (required for `"promote"`) |
| Response | `201 Created` with `DistillResultOut` — `new_preset_id`, `new_preset_slug`, `new_preset_name`, `manifest_preview` (5 fields), `aggregated_memory`, `source_entity_id`, `source_preset_slug` |
| Behavior by action | **transmute**: reads entity Memory, creates a new BaseClass row. **promote**: reads Instance runtime state, creates or updates an Entity row (no BaseClass row created). |
| Events | `LEARNING_DISTILLATION_COMPLETED` (type `"learning.distillation_completed"`) — payload includes `entity_id`, `new_preset_slug`, `source_preset_slug`, `aggregated_counts`, `action` |
| Error cases | 404 (entity not found), 403 (insufficient role), 409 (slug already taken), 422 (no memory entries / missing `instance_id` for promote) |

### GET `/presets/{preset_id}`

| Aspect | Detail |
|--------|--------|
| Permission | Any authenticated user |
| Response | `DistillResultOut` — reads an existing BaseClass row and returns it in distill result format. `aggregated_memory` is zeroed; `source_entity_id` is empty |
| Events | None (read-only) |

## 6. P11+ Follow-ups

The P10 heuristic engine is intentionally the simplest viable implementation. The pluggable `DistillationEngine` Protocol makes the following upgrades straightforward:

| Item | Description | Effort |
|------|-------------|--------|
| **LLMDistiller** | Replace `AggregatingDistiller` with an LLM-based engine that reads memory entries and generates a prompt/skills/commands via chat completion. Uses the same `DistillationEngine` Protocol. | Medium |
| **Promote implementation** | `/promote` is registered but has no handler. Needs Instance runtime state extraction and Entity creation logic. | Medium |
| **Version control** | Track which BaseClass was the source for each transmutation (already stored in `manifest.source_preset_slug`). Add a `parent_preset_id` FK for lineage querying. | Small |
| **Multi-entity distill** | Transmute from multiple entities' memory into a shared BaseClass. Extends `DistillRequest` with `source_entity_ids: list[str]`. | Medium |
| **Scheduled distillation** | Add a background task (APScheduler or similar) that runs transmutation on a cron schedule. Enables "weekly skill extraction" workflows without manual commands. | Medium |
| **`/consolidate` implementation** | Merge multiple existing BaseClasses into a combined one. Registered as a `LEARNING_COMMAND` but no handler yet. | Small-Medium |
| **`/reflect` implementation** | Generate a retrospective summary from an entity's memory entries without creating a new BaseClass. | Small |
| **PresetRegistry refresh on distill** | After `POST /distill` creates a new BaseClass, call `registry.reload()` to make it immediately available for entity assignment. | Small |

## 7. 15d Rename Map

The table below maps every legacy code name to its 15d target name. Source code and API paths will be updated in the 15d-rename wave.

| Legacy (current code) | 15d Target | Scope |
|------------------------|------------|-------|
| `EmployeePreset` | `BaseClass` | Model, table, routes, tests |
| `Employee` | `Entity` | Model, table, routes, tests |
| `Office` | `Workspace` | Model, table, routes, tests |
| `MemoryEntry` | `Memory` | Model, table, routes, tests |
| `/distill` command | `/transmute` + `/promote` | Command family, directive router |
| `require_office_role` | `require_workspace_role` | Permission checker |
| `employee-presets` API path | `base-classes` API path | FastAPI route prefix |
| `employees` API path | `entities` API path | FastAPI route prefix |
| `offices` API path | `workspaces` API path | FastAPI route prefix |

**API paths in this document** (§5) use the legacy code names to match the current running codebase. The path structure (resource hierarchy, HTTP methods, query parameters) is unchanged — only the segment names will change.
