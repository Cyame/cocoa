"""Legacy notepad_refs migration — v4-6-learning-writeback.md 存量迁移.

Converts pre-v4.6 ``instance_loop_states.notepad_refs`` values that point
at file paths (the old harness notepad mirror) into real
``Memory(kind=notepad)`` rows, then rewrites the refs to memory ids::

    {"learnings": "/ws/.omo/notepads/plan/learnings.md"}  →  {"learnings": "<memory_id>"}

Rules (from the v4.6 plan):

- Values that already look like memory UUIDs are kept as-is (idempotent).
- A string value is treated as a file path: if readable, its content becomes
  the Memory ``content``; if not readable, ``content`` falls back to the path
  string and a ``learning.notepad_migration_orphan`` event is recorded.
- A list value is treated as multiple file paths — one Memory row per path.
- Rows whose Instance has no ``entity_id`` cannot create Memory rows
  (``entity_id`` is a required FK, H4) — their refs are left untouched and
  counted as skipped.

Entry points mirror :mod:`app.core.cerebellum_migration`:

- :func:`migrate_notepad_refs` — plain-sync core-SQL function the Alembic
  revision runs inside the migration transaction via ``op.get_bind()``; also
  unit-testable against an async connection via ``await conn.run_sync(...)``.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa

from app.models.event import Event
from app.models.instance import Instance
from app.models.loop_state import InstanceLoopState
from app.models.memory import Memory

logger = logging.getLogger(__name__)

LOOP_STATE = InstanceLoopState.__table__
INSTANCE = Instance.__table__
MEMORY = Memory.__table__
EVENT = Event.__table__

ORPHAN_EVENT_TYPE = "learning.notepad_migration_orphan"
_NOTEPAD_KIND = "notepad"


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _read_text(path: str) -> str | None:
    """Read *path* as UTF-8 text; ``None`` when unreadable."""
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return fp.read()
    except (OSError, UnicodeDecodeError):
        return None


def _iter_paths(value: Any) -> list[str]:
    """Normalize a refs value into a list of path strings."""
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str) and v]
    if isinstance(value, str) and value:
        return [value]
    return []


def migrate_notepad_refs(conn: sa.Connection) -> dict[str, int]:
    """Migrate legacy ``notepad_refs`` file-path structure to memory ids.

    Runs inside a transaction (Alembic wraps ``op.get_bind()`` in one by
    default). Never physically deletes rows. Returns a report dict.
    """
    report: dict[str, int] = {
        "scanned": 0,
        "memories_created": 0,
        "refs_rewritten": 0,
        "orphaned": 0,
        "skipped_no_entity": 0,
    }

    rows = conn.execute(
        sa.select(LOOP_STATE).where(LOOP_STATE.c.notepad_refs.isnot(None))
    ).mappings().all()

    instances = {
        row["id"]: row
        for row in conn.execute(sa.select(INSTANCE)).mappings()
    }

    for ls in rows:
        refs = ls["notepad_refs"]
        if not isinstance(refs, dict) or not refs:
            continue
        report["scanned"] += 1

        instance = instances.get(ls["instance_id"])
        entity_id = instance.get("entity_id") if instance is not None else None
        if not entity_id:
            report["skipped_no_entity"] += 1
            logger.warning(
                "notepad migration: loop_state %s instance %s has no entity_id — skipped",
                ls["id"], ls["instance_id"],
            )
            continue

        new_refs: dict[str, str] = {}
        now = datetime.now(timezone.utc)
        for name, value in refs.items():
            if isinstance(value, str) and _is_uuid(value):
                new_refs[name] = value
                continue

            memory_id: str | None = None
            for path in _iter_paths(value):
                content = _read_text(path)
                if content is None:
                    conn.execute(
                        sa.insert(EVENT).values(
                            id=str(uuid.uuid4()),
                            type=ORPHAN_EVENT_TYPE,
                            actor_type="system",
                            actor_id=None,
                            resource_type="memory",
                            resource_id=None,
                            payload={
                                "loop_state_id": ls["id"],
                                "instance_id": ls["instance_id"],
                                "notepad_name": name,
                                "path": path,
                            },
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    report["orphaned"] += 1
                    content = path
                memory_id = str(uuid.uuid4())
                conn.execute(
                    sa.insert(MEMORY).values(
                        id=memory_id,
                        entity_id=entity_id,
                        kind=_NOTEPAD_KIND,
                        key=f"notepad/{name}",
                        content=content,
                        source_instance_id=ls["instance_id"],
                        created_at=now,
                    )
                )
                report["memories_created"] += 1

            if memory_id is not None:
                new_refs[name] = memory_id

        conn.execute(
            sa.text(
                "UPDATE instance_loop_states SET notepad_refs = CAST(:refs AS JSON),"
                " updated_at = now() WHERE id = :id"
            ),
            {"refs": json.dumps(new_refs), "id": ls["id"]},
        )
        report["refs_rewritten"] += 1

    return report
