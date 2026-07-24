# Cocoa Terminology Glossary

One-line definitions for every Cocoa code-term, concept, and protocol entity. Derived from the metaphor name table (the anchor) and the core domain model. Code-terms stay English; display-names in parentheses are for product UI reference.

## Structure Terms

- **Office** (菌落) -- Organizational container for a workspace, holding multiple employee instances within a bounded colony.
- **Employee** (细胞) -- Persistent role identity defined by a preset manifest and shared cross-instance memory; one Employee can have N Instances.
- **Instance** (分身) -- A materialization of an Employee in one Office, with its own isolated workspace and runtime state.
- **Preset** (灵格) -- Employee template defining skills, tools, model, and instructions; selected at Employee creation time.
- **Gene** (基因) -- Learnable skill module, injectable into an Employee preset, produced by `/distill` from Memory.
- **Memory** (基因组) -- Employee-shared cumulative experience, appended cross-instance, not hot-loaded into session context.
- **Blackboard** (共生面) -- Per-Office shared real-time collaboration panel with permission-gated file read/write.
- **Vault** (冰封库) -- Cold storage archive for long-term preservation, written by `/archive` command.
- **Corridor** (突触) -- Adjacency edge between two Memberships in an Office, defining the selectable neighbor set for messaging.
- **Ring** (环) -- Explicit collaboration ring with bounded context scope; deferred to P3/P4, current placeholder.

## Presets

- **Planner** (密士) -- Plans and decomposes tasks; preset registry owns `/plan`.
- **Worker** (铸金) -- Executes and builds; stateless or persistent depending on rank.
- **Oracle** (灵视) -- Reviews and verifies outputs; preset registry owns `/review`.
- **Explorer** (游魂) -- Explores and researches; preset registry owns `/search`.
- **Reviewer** (衡判) -- Judges and adjudicates; preset registry owns `/judge`.
- **Human** (总监) -- Human operator at Director rank, holds approval authority.

## Lab Ranks

- **Intern** (实习生) -- Stateless hot-load rank: no persistent session, no memory read, fresh invocation each time.
- **Researcher** (研究员) -- Full preset plus memory rank: persistent, accumulates experience across invocations.
- **Director** (总监) -- Human operator rank: highest authority, approval and forwarding rights.

## Sub-entities

Code-term-only data-layer entities from the P2 core domain model. No product UI display-names.

- **User** -- Human authentication identity: username, email, password hash; the login entity.
- **EmployeePreset** -- Persisted preset record storing slug, manifest JSONB, and version; forward contract to P3.
- **Membership** -- Employee or User membership in an Office, with hex coordinates, role, and permissions; exclusive-FK (exactly one of user_id or instance_id).
- **BlackboardFile** -- File record on a Blackboard, with storage key, content type, and directory tree metadata.
- **VaultEntry** -- Archived entry in a Vault, recording source type, source reference, and archival timestamp.
- **MemoryEntry** -- Append-only memory log entry per Employee, indexed by kind and time; no updated_at column.

## Concepts

- **Employee-as-role-identity** -- Employee is a persistent role identity composed of a preset manifest plus shared cross-instance memory; it grows as memory accumulates.
- **Instance=materialization** -- An Instance is a concrete materialization of an Employee in one Office, with isolated workspace and runtime.
- **near-neighbor messaging** -- Messaging restricted to corridor-defined adjacent nodes only; no broadcast fan-out, unlike flat log-based group chat.
- **corridor** -- The editable neighbor set of a node; defines the selectable recipient list for directed messaging within an Office.
- **activation trigger** -- Event that causes a node to sync topology and state: daily-report self-sync, on-mention, or scheduled task invocation.
- **/distill** -- Slash command that consolidates Memory entries into a learnable Gene, injectable into the Employee's preset.
- **slash-protocol** -- Structured turn-based command grammar: a Turn is a list of Directives, each with optional target, command, args, and content-ref.
- **directive** -- A single command unit within a Turn: target_employee, cmd, args, content_ref, and raw_text (Pydantic schema in `app/schemas/slash.py`).
- **command-registry** -- Dual registry of global commands (scope ops: `/read`, `/list`, `/write`, `/archive`) and per-preset commands defined in each preset manifest (forward contract to P3).
- **content-ref** -- A scope-qualified reference to content: mandatory scope prefix (workspace|blackboard|vault|memory) with optional path (Pydantic schema in `app/schemas/slash.py`).
- **composer compartmentalization** -- The P8 composer UI splits a message into per-employee compartments before send; the user sees and confirms what each employee receives, emitted as a structured Turn.