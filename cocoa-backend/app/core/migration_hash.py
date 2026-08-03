"""Migration-hash helper for the phase-15f capability lifecycle.

The ``migration_hash`` field on :class:`app.models.entity.Entity` is a
deterministic SHA-256 fingerprint of the entity's current *effective*
capability surface (the list of capability dicts + the prompt regen
snapshot). It is the source of truth for "is this instance still in
sync with the entity it belongs to?" — see PRD §13.6.4.

Formula
-------
::

    capabilities_json = json.dumps(sorted(capabilities_list), separators=(\",\", \":\"))
    prompt_sha        = sha256(prompt_regen_snapshot or \"\").hexdigest()
    migration_hash    = sha256(capabilities_json + \":\" + prompt_sha).hexdigest()

Notes
-----
* The capabilities list is sorted *before* JSON serialization so two
  Entity rows with the same capabilities in different insertion order
  produce the same hash.
* The prompt snapshot is hashed *separately* (not concatenated to the
  JSON) to keep the hash input short and avoid pathological cases where
  a 10 MB prompt snapshot swallows the capability bytes in a single
  buffer.
* The delimiter is a single ``\":\"`` character — neither a JSON nor a
  hex character — so two inputs can never collide without intent.
* Both fields are nullable / empty-defaultable, so the helper accepts
  ``None`` for both and produces a stable hash.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity

_CAPABILITIES_SEPARATOR = (",", ":")
_PROMPT_DELIMITER = ":"


def _prompt_sha(prompt_snapshot: str | None) -> str:
    """Return the SHA-256 hex digest of *prompt_snapshot* (empty if None)."""
    return hashlib.sha256((prompt_snapshot or "").encode("utf-8")).hexdigest()


def _normalize_capabilities(capabilities: Iterable[dict] | None) -> list[dict]:
    """Return a sorted, JSON-serialisable copy of *capabilities*.

    Sorting uses ``json.dumps(...)`` as the sort key so that the order
    is stable across processes (Python's ``sorted`` of dicts is not
    deterministic across heterogeneous dict bodies, but the JSON-string
    form is).
    """
    if not capabilities:
        return []
    return sorted(
        capabilities,
        key=lambda c: json.dumps(c, sort_keys=True, separators=_CAPABILITIES_SEPARATOR),
    )


def compute_migration_hash(
    capabilities: Iterable[dict] | None,
    prompt_snapshot: str | None,
) -> str:
    """Compute the SHA-256 migration hash for an arbitrary capability set.

    Parameters
    ----------
    capabilities:
        Iterable of capability dicts (the same shape stored on
        ``Entity.capabilities``). ``None`` and empty iterables both
        hash to the same value.
    prompt_snapshot:
        The prompt snapshot string (or ``None``).

    Returns
    -------
    64-character hex digest of the SHA-256 hash.
    """
    normalized = _normalize_capabilities(capabilities)
    capabilities_json = json.dumps(normalized, separators=_CAPABILITIES_SEPARATOR)
    prompt_digest = _prompt_sha(prompt_snapshot)
    payload = f"{capabilities_json}{_PROMPT_DELIMITER}{prompt_digest}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def compute_entity_migration_hash(db: AsyncSession, entity: Entity) -> str:
    """Compute the migration hash for an :class:`Entity` instance.

    v4.0: the capability surface is read from the ``entity_capabilities``
    junction (the ``entities.capabilities`` JSONB column was dropped).
    """
    from app.core.capabilities import load_entity_capability_dicts

    caps = await load_entity_capability_dicts(db, entity.id)
    return compute_migration_hash(caps, entity.system_prompt)
