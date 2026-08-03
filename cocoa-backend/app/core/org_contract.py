"""OrganizationContract grant helpers (v4.0).

Used by workspace / organization creation flows and test fixtures to ensure
a user holds atomic grants on an Organization.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization_contract import (
    OrganizationContract,
    OrganizationContractGene,
)
from app.models.user_gene import UserGene


async def ensure_org_contract(
    db: AsyncSession,
    *,
    organization_id: str,
    user_id: str,
    source_pack: str | None = None,
) -> OrganizationContract:
    """Return the active OrgContract for (org, user), creating it if missing."""
    result = await db.execute(
        select(OrganizationContract).where(
            OrganizationContract.organization_id == organization_id,
            OrganizationContract.user_id == user_id,
            OrganizationContract.deleted_at.is_(None),
        )
    )
    contract = result.scalar_one_or_none()
    if contract is None:
        contract = OrganizationContract(
            organization_id=organization_id,
            user_id=user_id,
            source_pack=source_pack,
        )
        db.add(contract)
        await db.flush()
    return contract


async def grant_atoms(
    db: AsyncSession,
    contract_id: str,
    atom_slugs: list[str] | tuple[str, ...],
) -> None:
    """Attach atom genes to a contract (idempotent). Unknown slugs raise."""
    if not atom_slugs:
        return
    rows = (
        await db.execute(
            select(UserGene).where(
                UserGene.slug.in_(set(atom_slugs)),
                UserGene.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    by_slug = {g.slug: g for g in rows}
    missing = sorted(set(atom_slugs) - set(by_slug))
    if missing:
        raise ValueError(f"Unknown atom gene slug(s): {', '.join(missing)}")
    for slug in atom_slugs:
        gene = by_slug[slug]
        existing = await db.execute(
            select(OrganizationContractGene).where(
                OrganizationContractGene.contract_id == contract_id,
                OrganizationContractGene.user_gene_id == gene.id,
                OrganizationContractGene.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none() is None:
            db.add(
                OrganizationContractGene(contract_id=contract_id, user_gene_id=gene.id)
            )
    await db.flush()
