# Cocoa Domain Model

> **15d Naming Convention (July 2026)**
>
> Model names in this document follow the 15d rename:
> * `Office` to `Workspace`
> * `EmployeePreset` to `BaseClass`
> * `Employee` to `Entity`
> * `MemoryEntry` to `Memory`
> * `Corridor` to `Passage`
> * `InstanceLoopState` to `LoopState`
> * `CorridorNode` dropped (still exists in code as deprecated)
>
> Database table names, column names, and FK references remain unchanged.

## ER Diagram

```mermaid
classDiagram
    User "1" -- "N" Membership : user_id
    Entity "1" -- "N" Instance : employee_id
    Entity "1" -- "N" Memory : employee_id
    BaseClass "1" -- "N" Entity : preset_slug
    Workspace "1" -- "N" Membership : office_id
    Workspace "1" -- "1" Blackboard : office_id
    Workspace "1" -- "1" Vault : office_id
    Blackboard "1" -- "N" BlackboardFile : office_id
    Vault "1" -- "N" VaultEntry : vault_id
    Membership "1" -- "N" Passage : from_membership_id
    Membership "1" -- "N" Passage : to_membership_id

    class User {
        +id: UUID
        +username: str
        +email: str
        +password_hash: str
        +is_super_admin: bool
        +created_at: datetime
        +updated_at: datetime
        +deleted_at: datetime?
    }
    class BaseClass {
        +id: UUID
        +slug: str
        +name: str
        +manifest: JSONB?
        +version: str?
        +created_at: datetime
        +updated_at: datetime
        +deleted_at: datetime?
    }
    class Entity {
        +id: UUID
        +name: str
        +slug: str
        +preset_slug: str?
        +rank: enum(intern|researcher|director)
        +display_name: str?
        +display_color: str?
        +created_at: datetime
        +updated_at: datetime
        +deleted_at: datetime?
    }
    class Instance {
        +id: UUID
        +employee_id: FK → employees.id
        +office_id: FK → offices.id
        +workspace_path: str?
        +status: enum(creating|pending|deploying|running|restarting|failed|deleting)
        +runtime_config: JSON?
        +proxy_token: str?
        +created_at: datetime
        +updated_at: datetime
        +deleted_at: datetime?
    }
    class Workspace {
        +id: UUID
        +name: str
        +slug: str
        +blackboard_ref: str?
        +created_at: datetime
        +updated_at: datetime
        +deleted_at: datetime?
    }
    class Membership {
        +id: UUID
        +office_id: FK → offices.id
        +user_id: FK → users.id?
        +instance_id: FK → instances.id?
        +hex_q: int
        +hex_r: int
        +role: enum(owner|editor|viewer)
        +permissions: JSON?
        +created_at: datetime
        +updated_at: datetime
        +deleted_at: datetime?
    }
    class Passage {
        +id: UUID
        +office_id: FK → offices.id
        +from_membership_id: FK → memberships.id
        +to_membership_id: FK → memberships.id
        +is_active: bool
        +edge_meta: JSON?
        +created_at: datetime
        +updated_at: datetime
        +deleted_at: datetime?
    }
    class Blackboard {
        +id: UUID
        +office_id: FK → offices.id
        +content: TEXT?
        +manual_notes: TEXT?
        +created_at: datetime
        +updated_at: datetime
        +deleted_at: datetime?
    }
    class BlackboardFile {
        +id: UUID
        +office_id: FK → offices.id
        +name: str
        +parent_path: str?
        +storage_key: UUID
        +content_type: str?
        +file_size: int?
        +is_directory: bool
        +uploader_user_id: FK → users.id?
        +uploader_instance_id: FK → instances.id?
        +created_at: datetime
        +updated_at: datetime
        +deleted_at: datetime?
    }
    class Vault {
        +id: UUID
        +office_id: FK → offices.id
        +created_at: datetime
        +updated_at: datetime
        +deleted_at: datetime?
    }
    class VaultEntry {
        +id: UUID
        +vault_id: FK → vaults.id
        +source_type: enum(blackboard_file|workspace_file)
        +source_ref: str?
        +archived_key: str?
        +archived_at: datetime?
        +created_at: datetime
        +updated_at: datetime
        +deleted_at: datetime?
    }
    class Memory {
        +id: UUID
        +employee_id: FK → employees.id
        +kind: enum(experience|lesson|decision|problem)
        +key: str?
        +content: TEXT?
        +source_instance_id: str?
        +created_at: datetime
        +deleted_at: datetime?
        -updated_at: (removed - append-only, no UPDATE path)
    }
```

## Cardinality Table

| Entity A | Cardinality | Entity B | Foreign Key / Join | Notes |
|----------|------------|----------|-------------------|-------|
| User | 1 : N | Membership | `memberships.user_id` | Exclusive-FK: user_id XOR instance_id; one user may belong to many workspaces |
| BaseClass | 1 : N | Entity | `employees.preset_slug` (soft ref) | Slug-based reference, NOT a formal FK to `employee_presets.id`; base class can be deleted or re-versioned independently |
| Entity | 1 : N | Instance | `instances.employee_id` | One entity spawns multiple instances across workspaces |
| Entity | 1 : N | Memory | `memory_entries.employee_id` | Append-only log; entries are never updated |
| Workspace | 1 : N | Instance | `instances.office_id` | Instance is bound to exactly one workspace |
| Workspace | 1 : N | Membership | `memberships.office_id` | Users and instances join a workspace through a membership record |
| Workspace | 1 : 1 | Blackboard | `blackboards.office_id` | Partial unique on `(office_id)` where `deleted_at IS NULL` |
| Workspace | 1 : 1 | Vault | `vaults.office_id` | Partial unique on `(office_id)` where `deleted_at IS NULL` |
| Blackboard | 1 : N | BlackboardFile | `blackboard_files.office_id` | Files belong to the same workspace, keyed by `(office_id, parent_path, name)` |
| Vault | 1 : N | VaultEntry | `vault_entries.vault_id` | Each entry tracks what was archived, when, and the retrieval key |
| Membership | 1 : N | Passage (from) | `corridors.from_membership_id` | Directed edge in the adjacency graph |
| Membership | 1 : N | Passage (to) | `corridors.to_membership_id` | Directed edge in the adjacency graph |

### Implicit relationships (no dedicated FK, navigated via intermediate entity)

| Path | Notes |
|------|-------|
| Instance → Workspace | Via `instances.office_id` FK (not diagrammed as a separate edge - Instance is always owned by one Workspace) |
| Instance → Membership | Via `memberships.instance_id` (exclusive-FK, instance membership in a workspace) |
| User → Instance | No direct FK; a User acts on an Instance through Workspace membership |

## Entity Summary (with metaphor names)

| Table | Code Term | Bio-Name | Display Name | Description |
|-------|-----------|----------|-------------|-------------|
| `users` | User | - | - | Human authentication identity |
| `employee_presets` | BaseClass | - | 灵格 | Reusable base class template with manifest and version |
| `employees` | Entity | 细胞 | 细胞 | Persistent agent identity with rank and base class |
| `instances` | Instance | 分身 | 分身 | Entity runtime in a specific workspace |
| `offices` | Workspace | 菌落 | 菌落 | Collaboration workspace boundary |
| `memberships` | Membership | - | - | User or Instance presence in a Workspace with role + hex coords |
| `corridors` | Passage | 突触 | 突触 | Directed adjacency edge between memberships |
| `blackboards` | Blackboard | 共生面 | 黑板 | 1:1 shared collaboration context per Workspace |
| `blackboard_files` | BlackboardFile | - | - | File/directory within a Blackboard |
| `vaults` | Vault | 冰封库 | 冰封库 | 1:1 cold archival storage per Workspace |
| `vault_entries` | VaultEntry | - | - | Archived artifact entry |
| `memory_entries` | Memory | 基因组 | 基因组 | Append-only entity memory log |

## Progression: BaseClass to Entity to Instance

The core resource pipeline moves through three stages:

1. **BaseClass** - A reusable template with a manifest (model, prompt, skills, tools, commands). Defines what an agent _can be_. Slug-referenced from Entity records (no FK), so base classes can be versioned or deleted independently.
2. **Entity** - A named, ranked agent identity assigned a base class. Carries persistent memory (`Memory` entries) that accumulates across instances. An entity is the durable agent record.
3. **Instance** - A materialized runtime of an entity inside a specific workspace. Bound to exactly one workspace via `office_id`. Has a lifecycle state machine (creating, pending, deploying, running, restarting, failed, deleting). Each instance gets its own filesystem path (`workspace_path`) and optional proxy token.

## Directory Contract Summary

At P2 scope, the system defines these content scopes (aligned with `ContentRef.scope` in the slash protocol schema):

| Scope | Target | Read/Write | Persistence |
|-------|--------|-----------|-------------|
| `workspace` | Instance filesystem (`instances.workspace_path`) | Read + Write | Tied to Instance lifecycle |
| `blackboard` | `blackboards.content` / `manual_notes` + `blackboard_files` | Read + Write (permission-gated via Membership role) | Survives Instance restarts; per-Workspace |
| `vault` | `vault_entries` (cold storage) | Read-only (write via `/archive` command) | Permanent archive per Workspace |
| `memory` | `memory_entries` (entity log) | Read + Append (no update) | Cross-Instance for the Entity |

Files within `blackboard` scope are represented as `BlackboardFile` rows with a virtual directory tree keyed by `(office_id, parent_path, name)`. The `storage_key` is a globally unique UUID referencing the underlying object store.

## Slash-Protocol Summary

The slash protocol (`app/schemas/slash.py`) defines three Pydantic models as a forward contract for P4's parser:

- **`ContentRef`** - Points to content in one of four scopes: `workspace`, `blackboard`, `vault`, or `memory`. Has a mandatory `scope` field and optional `path`.
- **`Directive`** - A single command within a Turn: `target_employee` (optional agent target), `cmd` (verb, e.g. `/read`), `args` (positional), optional `content_ref`, and `raw_text` (populated by P4 parser).
- **`Turn`** - A user utterance decomposed into a list of `Directive` objects plus `general_text` for free-form content that does not parse into any directive.
- **`CommandRegistry`** - Placeholder shape for the global command list and per-base-class overrides. Final schema owned by P4.

At P2, these schemas are structural definitions only - no parsing logic exists. They are consumed by API endpoints that accept pre-parsed directive lists.

## Forward-Contract Notes

| Concern | Phase | Detail |
|---------|-------|--------|
| `BaseClass.manifest` (JSONB) | P4 | The `manifest` field stores base class definition data (skills, tools, model, instructions). Its internal schema will be defined in P4 when base classes become active. At P2 it is nullable and untyped. |
| `CommandRegistry` | P4 | The `CommandRegistry` schema in `slash.py` is a placeholder. P4's slash-parser module will own the final command list, per-base-class overrides, and command validation logic. |
| Slash protocol parser | P4 | Raw text to `Turn`/`Directive` parsing is a P4 concern. P2 only validates pre-parsed objects. |
| Passage acyclicity | P5 | The Passage adjacency graph currently has no cycle-detection at the DB level. A service-layer acyclicity check is planned for P5 (checking for closed loops when edges are added). |
| Ring (环) topology | P5 | The Ring concept is named in the metaphor table but has no corresponding DB table. It is a higher-level grouping of Memberships for explicit collaboration rings (deferred to P5 messaging-topology phase). |

## Key Design Decisions

### 1. Soft-Delete with Partial Unique Indexes

All 12 tables use soft-delete via `BaseModel.deleted_at` (nullable `DateTime(timezone=True)`). Physical deletion (`DELETE FROM`) is never used. This means every unique constraint must be a **Partial Unique Index** filtered by `WHERE deleted_at IS NULL` - otherwise a soft-deleted record would permanently block re-creation of an equivalent active record.

Examples from the schema:

- `uq_offices_slug` - `UNIQUE (slug) WHERE deleted_at IS NULL`
- `uq_memberships_office_user` - `UNIQUE (office_id, user_id) WHERE deleted_at IS NULL AND user_id IS NOT NULL`
- `uq_blackboards_office` - `UNIQUE (office_id) WHERE deleted_at IS NULL`

The `uq_blackboard_files_storage_key` index is the exception - it applies globally (no `deleted_at` filter) because `storage_key` values must be unique even among soft-deleted files.

### 2. Exclusive-FK (XOR) Constraints

Two tables enforce that exactly one of two foreign keys is non-null:

- **`memberships`** - `user_id IS NOT NULL <> instance_id IS NOT NULL` (`ck_memberships_exclusive_fk`). A Membership represents EITHER a human user OR an agent instance, never both.
- **`blackboard_files`** - `uploader_user_id IS NOT NULL <> uploader_instance_id IS NOT NULL` (`ck_blackboard_files_exclusive_uploader`). A file uploader is EITHER a human OR an instance.

This pattern avoids nullable-column ambiguity and enforces domain semantics at the database level.

### 3. Append-Only Memory

`Memory` overrides `BaseModel.updated_at = None`, removing the column entirely. This enforces immutability: once written, a memory entry cannot be modified. Deletion is still supported via the inherited `deleted_at` field.

The `source_instance_id` column is a plain VARCHAR (no FK constraint) because the referenced Instance may have been soft-deleted before the memory entry is read. The memory entry preserves the instance identity that generated it without requiring referential integrity.

### 4. BaseClass via Slug (No FK)

`Entity.preset_slug` references `BaseClass.slug` as a plain string, not a foreign key. This decouples the base class lifecycle from entities - base classes can be deleted or re-versioned without cascading to entity records. An entity with a stale `preset_slug` retains their last-known configuration at instantiation time.

### 5. Hex-Grid Positioning (Membership.hex_q / hex_r)

Memberships carry axial hex coordinates (`hex_q`, `hex_r`) for spatial layout in the workspace hex grid. These are plain integers with no DB-level adjacency constraints - the Passage edges define the actual communication topology. Coordinates provide a visual arrangement independent of the logical neighbor graph.

### 6. Passage as Directed Adjacency Edges

Each Passage is a directed edge between two memberships in the same workspace. The `is_active` flag allows edges to be disabled without deletion. The partial unique index `uq_corridors_active_edge` ensures at most one active edge exists between any `(office_id, from_membership_id, to_membership_id)` pair. Acyclicity enforcement is deferred to the application layer (P5).
