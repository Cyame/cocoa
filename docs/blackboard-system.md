# Blackboard System

> **Code rename pending (15d-rename wave)**: This doc describes target architecture (15d+). Current code uses old naming.

Cocoa P6 storage, vault, and memory layer — the passive data surface that records collaboration context and agent learning.

## 1. Blackboard Data Model

The Blackboard is a **passive state module** per D11 architecture. It stores no active control logic — behavior control belongs to P8 Harness Supervisor.

Each Workspace has exactly one Blackboard (1:1), created lazily on first access. The Blackboard exposes two text fields:

| Field | Purpose |
|-------|---------|
| `content` | System-generated collaboration summary (written by P8 harness) |
| `manual_notes` | Human-annotated notes |

Both start as `None`. P6 provides read/write API endpoints; content generation is deferred to P8.

```python
# app/models/blackboard.py
class Blackboard(BaseModel, Base):
    office_id: str          # FK → offices.id
    content: str | None     # System-generated summary
    manual_notes: str | None # Human annotations
```

**Lazy creation**: `GET /api/v1/blackboard/{office_id}` auto-creates both the Blackboard and its corresponding Vault if they don't exist. No separate initialization endpoint needed.

**Partial unique index**: `uq_blackboards_office` on `(office_id)` with `WHERE deleted_at IS NULL` — only one active Blackboard per workspace.

## 2. BlackboardFile Virtual Filesystem

A hierarchical, path-based virtual filesystem inside each Workspace's Blackboard. Files are addressed by `parent_path` + `name`, forming a tree:

```
/ (root)
├── docs/           (parent_path=None, name="docs", is_directory=True)
│   └── readme.txt  (parent_path="/docs", name="readme.txt")
└── data.json       (parent_path=None, name="data.json")
```

### Path Rules

- **Root level**: `parent_path IS NULL`
- **Nested**: `parent_path` is the **full path** of the parent directory (e.g., `"/docs"`)
- **Directory marker**: `is_directory=True` for directories; directories cannot have `content_type` or `file_size`
- **Storage reference**: `storage_key` is a UUID logical reference to physical storage (P7 implements actual storage). Auto-generated if not provided.
- **Uploader**: tracked via `uploader_user_id` or `uploader_instance_id` (XOR constraint)

### Key Indexes

- `uq_blackboard_files_path` — unique `(office_id, parent_path, name)` within active records, preventing duplicate names at the same level
- `uq_blackboard_files_storage_key` — globally unique storage key

### File Operations

| Operation | Endpoint | Notes |
|-----------|----------|-------|
| List | `GET /{office_id}/files?parent_path=` | Offset pagination, sorted by name |
| Get | `GET /{office_id}/files/{file_id}` | Single file by ID |
| Create | `POST /{office_id}/files` | 201; parent directory must exist |
| Update | `PATCH /{office_id}/files/{file_id}` | Rename or move (change parent_path) |
| Delete | `DELETE /{office_id}/files/{file_id}` | 204; non-empty directories return 409 |

## 3. Vault Archiving

The Vault provides long-term cold storage for BlackboardFiles (and future workspace files in P7). Each Workspace has one Vault (1:1), created lazily.

### Archive Flow (hot-to-cold migration)

```
POST /{office_id}/files/{file_id}/archive

1. Verify file exists (non-directory, not deleted)
2. Lock the file row (`SELECT ... FOR UPDATE`)
3. Find or create the Workspace's Vault
4. Create VaultEntry(source_type="blackboard_file", source_ref=file_id, archived_key=file.storage_key)
5. Soft-delete the BlackboardFile
6. Commit — entire operation is atomic within a single DB transaction
7. Return 201 + VaultEntryOut
```

The `archived_at` timestamp is set server-side via `func.now()`.

### VaultEntry Schema

```python
class VaultEntry(BaseModel, Base):
    vault_id: str           # FK → vaults.id
    source_type: str        # "blackboard_file" or "workspace_file"
    source_ref: str | None  # Original file ID
    archived_key: str | None # Storage key for retrieval
    archived_at: datetime | None
```

### Important: P6 does NOT implement:
- `workspace_file` archiving (P7)
- Physical file storage (storage_key is a logical reference)
- File content upload/download

## 4. Memory Append-Log

Entity-indexed, append-only memory records. Entries are **immutable** — no update or delete endpoints.

### Memory Kinds

| Kind | Purpose |
|------|---------|
| `experience` | Hands-on recollection (task, interaction, observation) |
| `lesson` | Generalized insight derived from experiences |
| `decision` | A choice made with rationale |
| `problem` | Encountered obstacle with resolution context |

### Key Features

- **Append-only**: `MemoryEntry.updated_at = None` — no UPDATE path exists
- **Keyed lookup**: `?key=some-key` returns the latest entry for that key (ordered by `created_at DESC`, limit 1)
- **Cursor pagination**: `?cursor=<base64>` with ascending `created_at` order
- **Kind filter**: `?kind=experience` restricts to a specific kind
- **Entity-scoped**: All queries require `employee_id`

```python
class MemoryEntry(BaseModel, Base):
    employee_id: str       # FK → employees.id
    kind: str              # experience | lesson | decision | problem
    key: str | None        # Optional key for keyed lookup
    content: str | None    # Free-form text content
    source_instance_id: str | None  # Originating agent instance
```

### Key Index

`ix_memory_entries_employee_created` on `(employee_id, created_at)` supports efficient cursor-based listing.

### P6 P6 allows any authenticated user to write any entity's memory. P7 will tighten this via `instance_proxy_token` when agents write their own memory.

## 5. Permission Model

Workspace-scoped, role-gated access control. Every Blackboard/BlackboardFile/Vault/Memory endpoint verifies the authenticated user's membership role in the target workspace.

### Role Hierarchy

```
owner (2) > editor (1) > viewer (0)
```

### Access Rules

| Operation | Minimum Role | Error on denial |
|-----------|-------------|-----------------|
| GET Blackboard | `viewer` | 403 `office.not_member` |
| PATCH Blackboard | `editor` | 403 `office.not_member` / `office.insufficient_role` |
| GET Files / Vault | `viewer` | 403 `office.not_member` |
| POST/PATCH/DELETE Files | `editor` | 403 `office.not_member` / `office.insufficient_role` |
| Archive File | `editor` | 403 `office.not_member` / `office.insufficient_role` |
| POST Memory | Any authenticated | (P6: permissive; P7: instance_proxy_token) |
| GET Memory | Any authenticated | (P6: permissive; requires employee_id) |

### How It Works

```python
# app/core/permissions.py
ROLE_ORDER = {"viewer": 0, "editor": 1, "owner": 2}

async def require_office_role(session, user_id, office_id, min_role) -> Membership:
    # 1. Look up active membership
    # 2. If no membership → ForbiddenError("office.not_member", 403)
    # 3. If role too low → ForbiddenError("office.insufficient_role", 403)
    # 4. Return membership on success
```

Each endpoint calls `require_office_role(db, current_user.user_id, office_id, min_role)` before any data access.

## 6. API Reference

All endpoints are prefixed with `/api/v1`.

### Blackboard

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/blackboard/{office_id}` | Lazy-get or create Blackboard | viewer+ |
| PATCH | `/blackboard/{office_id}` | Update content / manual_notes | editor+ |

### Blackboard Files

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/blackboard/{office_id}/files` | List files (offset, ?parent_path=) | viewer+ |
| GET | `/blackboard/{office_id}/files/{file_id}` | Get single file | viewer+ |
| POST | `/blackboard/{office_id}/files` | Create file/directory (201) | editor+ |
| PATCH | `/blackboard/{office_id}/files/{file_id}` | Rename or move | editor+ |
| DELETE | `/blackboard/{office_id}/files/{file_id}` | Soft-delete (204; 409 if non-empty dir) | editor+ |

### Vault

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/blackboard/{office_id}/vault` | Get or create Vault | viewer+ |
| GET | `/blackboard/{office_id}/vault/entries` | List entries (?source_type=) | viewer+ |
| POST | `/blackboard/{office_id}/files/{file_id}/archive` | Archive file to vault (201) | editor+ |

### Memory

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/memory/entries` | List entries (?employee_id=, ?key=, ?kind=, ?cursor=) | authenticated |
| POST | `/memory/entries` | Append entry (201) | authenticated |

### Standard Error Responses

All endpoints return the standard Cocoa error envelope:

```json
{
    "error_code": "office.not_member",
    "message_key": "errors.office.not_member",
    "message": "You are not a member of this workspace",
    "details": {"user_id": "...", "office_id": "..."},
    "request_id": "..."
}
```

Common P6 error codes:

| Code | HTTP | Trigger |
|------|------|---------|
| `office.not_member` | 403 | User has no membership in target workspace |
| `office.insufficient_role` | 403 | User's role is below required minimum |
| `blackboard.file_not_found` | 404 | File ID does not exist or is deleted |
| `blackboard.directory_not_found` | 404 | Parent directory path does not exist |
| `blackboard.duplicate_path` | 409 | File/directory with same name already exists |
| `blackboard.directory_not_empty` | 409 | Cannot delete directory with children |
| `blackboard.cannot_archive_directory` | 409 | Cannot archive a directory entry |

### Event Types

| Event | Emitted By |
|-------|-----------|
| `blackboard.file_created` | POST /files |
| `blackboard.file_updated` | PATCH /files/{id} |
| `blackboard.file_archived` | POST /files/{id}/archive |
| `memory.entry_appended` | POST /memory/entries |

All events are persisted to the `events` table within the same transaction as the data mutation (commit-proximity contract).
