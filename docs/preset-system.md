# Preset System

> Agent preset templates (灵格) for Cocoa. Defines the manifest schema, built-in
> presets, command registry, slash-protocol grammar, selection gate, and registry
> loading lifecycle.

---

## 1. Preset Manifest Schema

Every `EmployeePreset` row carries a `manifest` JSONB column conforming to the
`PresetManifest` Pydantic schema (`app/schemas/preset.py`).

### Fields

| Field       | Type                     | Required | Description |
|-------------|--------------------------|----------|-------------|
| `version`   | `Literal["1.0"]`         | Yes      | Schema version; bump on breaking change |
| `llm`       | `LLMConfig`              | Yes      | LLM configuration (placeholder until P8) |
| `dirs`      | `dict[str, str]`         | No       | Per-preset directory overrides |
| `commands`  | `list[CommandSpec]`      | No       | Per-preset slash commands |

### CommandSpec

Each command entry is a dict with two fields:

```json
{"name": "plan", "description": "Break down a goal into actionable steps"}
```

### Example JSON

```json
{
  "version": "1.0",
  "llm": {"config": "TODO P8"},
  "dirs": {},
  "commands": [
    {"name": "plan", "description": "Break down a goal into actionable steps"},
    {"name": "decompose", "description": "Split a task into sub-tasks"}
  ]
}
```

---

## 2. Six Built-in Presets

Cocoa ships with six built-in presets seeded into the `employee_presets` table
by Alembic migration `0b4e3562358d`. Their slugs use P1 Chinese naming.

| Slug        | Name   | Version | Commands |
|-------------|--------|---------|----------|
| `mi-shi`    | 密士   | 1.0.0   | plan, decompose, prioritize |
| `zhu-jin`   | 铸金   | 1.0.0   | execute, build, test |
| `ling-shi`  | 灵视   | 1.0.0   | analyze, predict, review |
| `you-hun`   | 游魂   | 1.0.0   | search, survey, report |
| `heng-pan`  | 衡判   | 1.0.0   | review, approve, reject |
| `zong-jian` | 总监   | 1.0.0   | approve, reject, delegate |

The seed migration is idempotent: it checks for existing slugs before inserting,
and its downgrade only deletes presets matching known built-in slugs.

---

## 3. Command Registry

The preset system maintains two tiers of commands that operate under the
slash-protocol.

### Global Commands

Available in every preset, defined in `app/core/preset_registry.py`:

| Command     | Description |
|-------------|-------------|
| `read`      | Read a resource by reference |
| `list`      | List resources matching criteria |
| `write`     | Write content to a target |
| `archive`   | Archive or soft-delete a resource |

> **Note:** `GLOBAL_COMMANDS` in `app/core/preset_registry.py` stores the verbs without a leading slash (e.g. `"read"`, not `"/read"`). The slash is added at parse/display time by the slash-protocol grammar (§4). A separate `CONTROL_COMMANDS` set (P8, e.g. `"/interrupt"`) does include the leading slash.

### Per-preset Commands

Defined inside each preset's `manifest.commands` list. These supplement the
global commands with preset-specific verbs (e.g. `plan`, `execute`, `analyze`).

### Dual Registry

- `registry.get_commands(slug)` merges nothing at the code level — it returns
  only the per-preset commands from the manifest. The runtime (P5+) is expected
  to present *both* global and per-preset commands to the user.
- `registry.is_global_command(cmd)` checks whether a given verb belongs to
  `GLOBAL_COMMANDS`.

---

## 4. Slash-Protocol Grammar

All agent commands are invoked via a slash-prefixed verb followed by an optional
target, optional content reference, and free-form content.

### EBNF

```ebnf
command      = "/" verb [ ":" target ] [ "@" content_ref ] [ " " content ] ;
verb         = global_verb | preset_verb ;
global_verb  = "read" | "list" | "write" | "archive" ;
preset_verb  = "plan" | "decompose" | "prioritize" | "execute" | "build"
             | "test" | "analyze" | "predict" | "review" | "search"
             | "survey" | "report" | "approve" | "reject" | "delegate" ;
target       = path_spec ;
content_ref  = word ;
content      = { any_character } ;
path_spec    = word ( "/" word )* ;
word         = letter { letter | digit | "-" | "_" } ;
```

### Examples

| Input | Verb | Target | Content Ref | Content |
|-------|------|--------|-------------|---------|
| `/plan` | plan | — | — | — |
| `/read:/tmp/report.md` | read | `/tmp/report.md` | — | — |
| `/write:/tmp/note.md@ref1 some content` | write | `/tmp/note.md` | ref1 | some content |
| `/review:PR-42` | review | PR-42 | — | — |
| `/delegate:task-1@msg-abc` | delegate | task-1 | msg-abc | — |

### Target Resolution

The `:target` segment identifies the resource the command operates on. It may be
a filesystem path, a database entity ID, or an abstract reference. Exact
resolution rules are defined per command implementation (P5+).

### Content Reference

The `@content_ref` segment points to additional data (e.g. a message ID, a
previous command output). When omitted, the command acts on the verb + target
alone.

---

## 5. Selection Gate

The selection gate validates that an `Employee` references a known, active
`EmployeePreset` on creation and update.

### Employee Creation

```text
if employee.preset_id is set:
    lookup EmployeePreset by preset_id
    if not found or deleted_at is not null:
        reject with 422 "preset not found"
```

### Employee Update

```text
if employee.preset_id changes:
    lookup EmployeePreset by new preset_id
    if not found or deleted_at is not null:
        reject with 422 "preset not found"
```

This rule ensures every employee is either preset-less (raw agent) or bound to a
valid template. The check runs inside the `POST /employees` and
`PATCH /employees/{id}` route handlers before committing.

---

## 6. Registry Loading

The `PresetRegistry` singleton (`app/core/preset_registry.py`) is an in-memory
cache of all active `EmployeePreset` rows.

### Lifespan Startup

```text
lifespan.startup:
    1. configure_logging()
    2. start task queue (InMemoryTaskQueue)
    3. schedule_daily_report_sync(queue)  ← P5 activation registration (P7.5)
    4. registry.load(db)                  ← load presets from DB
    5. emit system.startup                ← after registry is ready

lifespan.shutdown:
    1. emit system.shutdown
    2. queue.stop()
```

The registry is loaded *before* the `system.startup` event to guarantee it is
ready before the first HTTP request arrives. The `daily_report_sync` task is
scheduled on the queue before the registry load to ensure the P5 activation
trigger pipeline is wired (otherwise the consumer `messaging.activation_triggered`
events are emitted but no `daily_report_sync` task is registered to act on them).

### CRUD Reload

Every mutation endpoint in the employee-presets router calls
`registry.reload(db)` after a successful commit:

- `POST` → reload after insert
- `PATCH` → reload after update
- `DELETE` → reload after soft-delete

This keeps the cache consistent with the database without stale-window races
(the reload is synchronous within the request). The `reload()` method simply
re-executes `load()` — it replaces the entire `dict` atomically.
