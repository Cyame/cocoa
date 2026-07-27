# Cocoa Learning System

The P10 Learning layer is Cocoa's skill-distillation subsystem — the bridge between accumulated employee memory and reusable agent presets. It reads an employee's `MemoryEntry` records, distills them into a structured `PresetManifest`, and creates a new `EmployeePreset` row. This document covers the architecture, Protocol interface, default algorithm, command integration, API reference, and future directions.

## 1. Learning Subsystem Architecture

P10 sits at the intersection of three established subsystems: **Memory** (P6 append-only log), **EmployeePreset** (P4 manifest registry), and **Directive Routing** (P5 command dispatch). It does NOT modify any existing table — it only reads from `MemoryEntry` and writes new rows to `EmployeePreset`.

```
  Employee  ---(writes)---> MemoryEntry (append-only)
       |                          |
       |                    [Memory read]
       v                          v
  EmployeePreset  <--- AggregatingDistiller (heuristic engine)
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

- **Zero schema migration** — P2's `memory_entries` table (append-only, no `updated_at`) and `EmployeePreset.manifest` JSONB already support the required data shape. No new tables or columns.
- **New preset, not mutation** — Distillation creates a new `EmployeePreset` row with slug `{source_preset_slug or 'base'}-skill-{target_skill_slug}`. The source preset remains unchanged, enabling A/B testing and rollback.
- **Engine does not write DB** — `DistillationEngine.distill()` returns a pure `DistillResult` dataclass. API endpoints handle persistence, slug uniqueness checks, and event emission. This matches the P8 harness handler contract.
- **Explicit user trigger** — `/distill` is only invoked by the operator (API or slash command). No scheduled/auto-distill in P10.

## 2. DistillationEngine Protocol Interface Contract

The core abstraction is `DistillationEngine`, a `typing.Protocol` defined in `app/core/distillation.py`. Any class conforming to this interface can be substituted at runtime:

```python
class DistillationEngine(Protocol):
    async def distill(
        self,
        employee_id: str,
        *,
        request: DistillRequest,
        session: AsyncSession,
    ) -> DistillResult:
        ...
```

**Contract rules:**

| Rule | Detail |
|------|--------|
| Input | `employee_id` (UUID), `DistillRequest` (target slug + kind filter + source preset), `AsyncSession` |
| Output | `DistillResult` dataclass with `new_preset_slug`, `manifest_preview` (`SkillManifestPreview`), `aggregated_memory` (`AggregatedMemoryCount`), `source_employee_id`, `source_preset_slug` |
| No side effects | Must NOT commit, flush, or emit events — pure computation with read-only DB access |
| Error handling | Raise `DistillationError(code, message_key, message)` for recoverable failures (e.g., no memory entries) |
| Duck typing | The Protocol is structural; no `isinstance` check needed. Callers type-annotate with `DistillationEngine` for IDE/linter support |

**DistillRequest fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `target_skill_slug` | `str` | Yes | Kebab-case slug for the new skill (pattern `^[a-z][a-z0-9-]*$`) |
| `memory_kind_filter` | `list[str] \| None` | No | Which `MemoryKind` values to include. `None` = all four kinds |
| `source_preset_slug` | `str \| None` | No | Source preset to inherit `model` from; `None` = use `"tbd"` |
| `target_preset_name` | `str \| None` | No | Human-readable name; `None` = auto-generate `"Skill: {slug}"` |

## 3. AggregatingDistiller Algorithm

`AggregatingDistiller` is the default heuristic engine — stateless, deterministic, and pure. No LLM calls.

**Algorithm steps:**

1. **Look up Employee** by `employee_id`. Raise `DistillationError("employee.not_found", ...)` if missing.
2. **Query MemoryEntry** rows for the employee (`deleted_at IS NULL`), optionally filtered by `memory_kind_filter`.
3. **Raise if empty** — `DistillationError("learning.no_memory", ...)` when no entries match.
4. **Aggregate counts** by `MemoryKind` (experience / lesson / decision / problem) into `AggregatedMemoryCount`.
5. **Extract commands** from `lesson` and `decision` entries: keys matching kebab-case pattern (`^[a-z][a-z0-9-]+$`) are deduplicated and collected (max 10).
6. **Generate prompt** from the longest lesson content (>= 50 characters), truncated to 200 characters + `"..."`. Falls back to `"TODO P8"` if no qualifying lesson exists.
7. **Extract skills** from all entry keys: split on `-`, take the first segment, deduplicate.
8. **Model**: inherit from `source_preset.manifest["model"]` if `source_preset_slug` is provided and exists, otherwise `"tbd"`.
9. **Tools**: always empty (`[]`) — cannot be inferred from memory.
10. **Slug**: `f"{source_preset_slug or 'base'}-skill-{target_skill_slug}"`.

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
LEARNING_COMMANDS: list[str] = ["/distill", "/consolidate", "/reflect"]
```

| Family | Commands | Registered P | Route Target | Requires @target |
|--------|----------|-------------|--------------|-----------------|
| GLOBAL | `/read`, `/list`, `/write`, `/archive` | P4 | Message corridor | No |
| PER-PRESET | Defined in `manifest.commands` | P4 | Message corridor | Yes |
| CONTROL | `/interrupt`, `/pause`, `/resume`, `/status`, `/snapshot` | P8 | Harness Supervisor | Yes |
| **LEARNING** | `/distill`, `/consolidate`, `/reflect` | **P10** | **AggregatingDistiller** | **Yes** |

**P5 Routing Priority** (in `directive_router.py::route_turn()`):

```
is_control_command(cmd)  →  _route_control_directive()
is_learning_command(cmd)  →  _route_learning_directive()
is_global_command(cmd)  →  message corridor
per-preset command  →  message corridor
```

Control takes precedence over learning. Both require explicit `@target` (bare commands are silently dropped, matching P5 semantics). Learning is checked before global/per-preset so that `/distill` does not accidentally match a per-preset command of the same name.

In the P10 implementation, only `/distill` has a functional handler (`_route_learning_directive` in `directive_router.py`). `/consolidate` and `/reflect` are registered as valid command names but have no implementation yet — they are deferred to P11+.

## 5. Learning API Endpoints Reference

All endpoints are prefixed with `/api/v1/learning` and registered in `app/api/v1/router.py`.

### GET `/memories/{employee_id}/summary`

| Aspect | Detail |
|--------|--------|
| Permission | `require_office_role(..., "viewer")` — employee must belong to an office |
| Query params | `kind: list[str]` (multi-value filter), `limit: int` (1-200, default 50) |
| Response | `MemorySummaryOut` — `aggregated_counts` (per-kind ints + total), `sample_lessons` (<=5 lesson snippets), `sample_keys_by_kind` (<=5 per kind) |
| Events | None (read-only) |

### POST `/employees/{employee_id}/distill`

| Aspect | Detail |
|--------|--------|
| Permission | `require_office_role(..., "editor")` |
| Request body | `DistillRequest` — `target_skill_slug` (required), `memory_kind_filter`, `source_preset_slug`, `target_preset_name` |
| Response | `201 Created` with `DistillResultOut` — `new_preset_id`, `new_preset_slug`, `new_preset_name`, `manifest_preview` (5 fields), `aggregated_memory`, `source_employee_id`, `source_preset_slug` |
| Events | `LEARNING_DISTILLATION_COMPLETED` (type `"learning.distillation_completed"`) — payload includes `employee_id`, `new_preset_slug`, `source_preset_slug`, `aggregated_counts` |
| Error cases | 404 (employee not found), 403 (insufficient role), 409 (slug already taken), 422 (no memory entries) |

### GET `/presets/{preset_id}`

| Aspect | Detail |
|--------|--------|
| Permission | Any authenticated user |
| Response | `DistillResultOut` — reads an existing `EmployeePreset` row and returns it in distill result format. `aggregated_memory` is zeroed; `source_employee_id` is empty |
| Events | None (read-only) |

## 6. P11+ Follow-ups

The P10 heuristic engine is intentionally the simplest viable implementation. The pluggable `DistillationEngine` Protocol makes the following upgrades straightforward:

| Item | Description | Effort |
|------|-------------|--------|
| **LLMDistiller** | Replace `AggregatingDistiller` with an LLM-based engine that reads memory entries and generates a prompt/skills/commands via chat completion. Uses the same `DistillationEngine` Protocol. | Medium |
| **Version control** | Track which preset was the source for each distillation (already stored in `manifest.source_preset_slug`). Add a `parent_preset_id` FK for lineage querying. | Small |
| **Multi-employee distill** | Distill from multiple employees' memory entries into a shared preset. Extends `DistillRequest` with `source_employee_ids: list[str]`. | Medium |
| **Scheduled distillation** | Add a background task (APScheduler or similar) that runs distillation on a cron schedule. Enables "weekly skill extraction" workflows without manual `/distill`. | Medium |
| **`/consolidate` implementation** | Merge multiple existing presets into a combined one. Registered as a `LEARNING_COMMAND` but no handler yet. | Small-Medium |
| **`/reflect` implementation** | Generate a retrospective summary from an employee's memory entries without creating a new preset. | Small |
| **PresetRegistry refresh on distill** | After `POST /distill` creates a new preset, call `registry.reload()` to make it immediately available for employee assignment. | Small |
