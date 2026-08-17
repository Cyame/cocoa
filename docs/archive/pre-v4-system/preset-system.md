> **Pre-v4 reference**: Conflict with `.omo/evidence/audit-product-design.md` → audit wins. Awaiting v4 PRD rewrite.
>

# BaseClass System (Preset System)

> **Code rename pending (15d-rename wave)**: This doc describes target architecture (15d+). Current code uses old naming: `EmployeePreset` for BaseClass, `Employee` for Entity, `Office` for Workspace.

---

## 1. BaseClass Manifest Schema

Every `BaseClass` row carries a `manifest` JSONB column conforming to the
`PresetManifest` Pydantic schema (`app/schemas/preset.py`).

### Fields

| Field       | Type                     | Required | Description |
|-------------|--------------------------|----------|-------------|
| `version`   | `Literal["1.0"]`         | Yes      | Schema version; bump on breaking change |
| `llm`       | `LLMConfig`              | Yes      | LLM configuration (placeholder until P8) |
| `dirs`      | `dict[str, str]`         | No       | Per-baseclass directory overrides |
| `commands`  | `list[CommandSpec]`      | No       | Per-baseclass slash commands |

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

## 2. Eleven Built-in BaseClasses

Eyot ships with eleven built-in BaseClasses seeded into the `employee_presets`
table by Alembic migration. Their slugs use P1 Chinese naming.

| Slug        | Name   | Version | Commands |
|-------------|--------|---------|----------|
| `mi-shi`    | 密士   | 1.0.0   | plan, decompose, prioritize |
| `huan-ling` | 唤灵   | 1.0.0   | summon, converse, inspire |
| `an-xing`   | 暗行   | 1.0.0   | infiltrate, extract, surveil |
| `an-ying`   | 暗影   | 1.0.0   | shadow, mimic, veil |
| `zhu-jin`   | 铸金   | 1.0.0   | execute, build, test |
| `ling-shi`  | 灵视   | 1.0.0   | analyze, predict, review |
| `heng-pan`  | 衡判   | 1.0.0   | review, approve, reject |
| `you-hun`   | 游魂   | 1.0.0   | search, survey, report |
| `qian-zhi`  | 潜知   | 1.0.0   | learn, deduce, synthesize |
| `bai-tong`  | 百瞳   | 1.0.0   | correlate, detect, foresee |
| `jiu-ri`    | 旧日   | 1.0.0   | recall, reconstruct, prophesy |

The seed migration is idempotent: it checks for existing slugs before inserting,
and its downgrade only deletes BaseClasses matching known built-in slugs.

---

## 3. Command Registry

The BaseClass system maintains two tiers of commands that operate under the
slash-protocol.

### Global Commands

Available to every BaseClass, defined in `app/core/preset_registry.py`:

| Command     | Description |
|-------------|-------------|
| `/read`     | Read a resource by reference |
| `/list`     | List resources matching criteria |
| `/write`    | Write content to a target |
| `/archive`  | Archive or soft-delete a resource |

> **Note:** `GLOBAL_COMMANDS` in `app/core/preset_registry.py` stores verbs with a leading slash (for example, `"/read"`), matching the P4 parser's `Directive.cmd` output. `CONTROL_COMMANDS` follows the same convention (for example, `"/interrupt"`).

### Per-BaseClass Commands

Defined inside each BaseClass's `manifest.commands` list. These supplement the
global commands with BaseClass-specific verbs (e.g. `plan`, `execute`, `analyze`,
`summon`, `infiltrate`, `recall`).

### Dual Registry

- `registry.get_commands(slug)` merges nothing at the code level — it returns
  only the per-BaseClass commands from the manifest. The runtime (P5+) is expected
  to present *both* global and per-BaseClass commands to the user.
- `registry.is_global_command(cmd)` checks whether a given verb belongs to
  `GLOBAL_COMMANDS`.

---

## 4. Slash-Protocol Grammar

All agent commands are invoked via a slash-prefixed verb followed by an optional
target, optional content reference, and free-form content.

### EBNF

```ebnf
command      = "/" verb [ ":" target ] [ "@" content_ref ] [ " " content ] ;
verb         = global_verb | baseclass_verb ;
global_verb  = "read" | "list" | "write" | "archive" ;
baseclass_verb = "plan" | "decompose" | "prioritize" | "execute" | "build"
              | "test" | "analyze" | "predict" | "review" | "search"
              | "survey" | "report" | "approve" | "reject" | "summon"
              | "converse" | "inspire" | "infiltrate" | "extract" | "surveil"
              | "shadow" | "mimic" | "veil" | "learn" | "deduce"
              | "synthesize" | "correlate" | "detect" | "foresee"
              | "recall" | "reconstruct" | "prophesy" ;
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
| `/summon:assistant-1@msg-abc` | summon | assistant-1 | msg-abc | — |

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

The selection gate validates that an Entity references a known, active
BaseClass on creation and update.

### Entity Creation

```text
if entity.preset_id is set:
    lookup BaseClass by preset_id
    if not found or deleted_at is not null:
        reject with 422 "BaseClass not found"
```

### Entity Update

```text
if entity.preset_id changes:
    lookup BaseClass by new preset_id
    if not found or deleted_at is not null:
        reject with 422 "BaseClass not found"
```

This rule ensures every Entity is either BaseClass-less (raw agent) or bound to a
valid template. The check runs inside the `POST /employees` and
`PATCH /employees/{id}` route handlers before committing.

---

## 6. Registry Loading

The `BaseClassRegistry` singleton (`app/core/preset_registry.py`) is an in-memory
cache of all active `BaseClass` rows.

### Lifespan Startup

```text
lifespan.startup:
    1. configure_logging()
    2. start task queue (InMemoryTaskQueue)
    3. schedule_daily_report_sync(queue)  ← P5 activation registration (P7.5)
    4. registry.load(db)                  ← load BaseClasses from DB
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

Every mutation endpoint in the BaseClass router calls `registry.reload(db)` after
a successful commit:

- `POST` → reload after insert
- `PATCH` → reload after update
- `DELETE` → reload after soft-delete

This keeps the cache consistent with the database without stale-window races
(the reload is synchronous within the request). The `reload()` method simply
re-executes `load()` — it replaces the entire `dict` atomically.

---

## 7. Distillation: Learning → BaseClass Creation

The Learning subsystem (P10) converts accumulated Entity memory into reusable
BaseClasses through two distinct actions:

### Promote (晋升)

**In-place Entity enhancement.** Adds new capabilities to an existing Entity's
BaseClass manifest without creating a separate template. The Entity retains its
identity and Workspace membership while its command repertoire expands.

### Transmute (炼化)

**Entity → BaseClass creation.** Extracts a new BaseClass from an Entity's
accumulated memory. This produces a standalone template (`{source}-skill-{target}`
slug) that can be assigned to any Entity in the Workspace. The transmuted
BaseClass inherits the source BaseClass as its parent lineage.

The `AggregatingDistiller` heuristic engine (no LLM) drives both actions by
analyzing per-kind memory counts and recent lesson snippets to generate
commands, skills, and a prompt.
