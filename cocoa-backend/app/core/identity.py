"""Platform identity (v4.0) — derived from flags + Contract atoms.

The PRD-v3-post identity **packs** (permission-carrying ``user_genes`` rows
such as ``identity-system``) were removed in v4.0: UserGene is now a
catalog-neutral atom table and tenant grants live on Contracts.

What remains:

- ``identity`` for API payloads is **derived**: ``"system"`` iff
  ``user.is_super_admin``, else ``None``. There are no locked gene packs.
- The ``extra_gene_slugs`` summary is the union of atomic grants across the
  user's Contracts (what the StatusBar gene labels display).
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import list_user_grant_slugs
from app.models.user import User

IdentityKey = Literal["system", "org", "namespace", "workspace", "member"]

IDENTITY_ORDER: tuple[IdentityKey, ...] = (
    "system",
    "org",
    "namespace",
    "workspace",
    "member",
)


def rank_of(identity: IdentityKey) -> int:
    """Lower number = higher privilege."""
    return IDENTITY_ORDER.index(identity)


def highest_identity(keys: set[IdentityKey]) -> IdentityKey | None:
    if not keys:
        return None
    return min(keys, key=rank_of)


async def resolve_user_identity(
    db: AsyncSession, user_id: str
) -> tuple[IdentityKey | None, list[str], list[str]]:
    """Return (derived identity, locked slugs, granted atom slugs).

    Locked slugs are always empty — packs no longer exist; the list shape is
    kept for response-schema compatibility.
    """
    user = await db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        return None, [], []
    atoms = sorted(await list_user_grant_slugs(db, user_id))
    identity: IdentityKey | None = "system" if user.is_super_admin else None
    return identity, [], atoms
