"""NamespaceContract (契印) CRUD — v4.0 (atomic genes via junction)."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, NotFoundError
from app.core.gene_atoms import ATOM_CATALOG
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import require_permission
from app.models.namespace_contract import NamespaceContract, NamespaceContractGene
from app.models.organization import Namespace
from app.models.organization_contract import (
    OrganizationContract,
    OrganizationContractGene,
)
from app.models.user import User
from app.models.user_gene import UserGene
from app.schemas.namespace_contract import (
    NamespaceContractCreate,
    NamespaceContractGeneRef,
    NamespaceContractOut,
    NamespaceContractUpdate,
)

router = APIRouter(prefix="/namespaces", tags=["NamespaceContracts"])
add_error_responses(router)


async def _get_namespace(db: DB, namespace_id: str) -> Namespace:
    ns = await db.get(Namespace, namespace_id)
    if ns is None or ns.deleted_at is not None:
        raise NotFoundError(
            "namespace.not_found",
            "errors.namespace.not_found",
            f"Namespace '{namespace_id}' not found",
        )
    return ns


async def _atom_genes(db: DB, slugs: list[str]) -> dict[str, UserGene]:
    """Validate slugs against the atom catalog and return slug → gene."""
    unknown = sorted(set(slugs) - set(ATOM_CATALOG))
    if unknown:
        raise NotFoundError(
            "user_gene.not_found",
            "errors.user_gene.not_found",
            f"Unknown atom gene slug(s): {', '.join(unknown)}",
        )
    if not slugs:
        return {}
    rows = (
        await db.execute(
            select(UserGene).where(
                UserGene.slug.in_(set(slugs)),
                UserGene.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    return {g.slug: g for g in rows}


async def _ensure_org_contract(db: DB, *, organization_id: str, user_id: str) -> None:
    """Design §13.2: an NS contract requires a parent OrgContract.

    Auto-creates a view-only OrgContract when missing (mirrors the v4.0
    data-migration fallback).
    """
    existing = await db.execute(
        select(OrganizationContract).where(
            OrganizationContract.organization_id == organization_id,
            OrganizationContract.user_id == user_id,
            OrganizationContract.deleted_at.is_(None),
        )
    )
    contract = existing.scalar_one_or_none()
    if contract is None:
        contract = OrganizationContract(
            organization_id=organization_id,
            user_id=user_id,
        )
        db.add(contract)
        await db.flush()
    view_gene = (
        await db.execute(
            select(UserGene).where(
                UserGene.slug == "can_view_workspace",
                UserGene.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if view_gene is not None:
        link = await db.execute(
            select(OrganizationContractGene).where(
                OrganizationContractGene.contract_id == contract.id,
                OrganizationContractGene.user_gene_id == view_gene.id,
                OrganizationContractGene.deleted_at.is_(None),
            )
        )
        if link.scalar_one_or_none() is None:
            db.add(
                OrganizationContractGene(
                    contract_id=contract.id,
                    user_gene_id=view_gene.id,
                )
            )
            await db.flush()


async def _contract_out(db: DB, contract: NamespaceContract) -> NamespaceContractOut:
    rows = (
        await db.execute(
            select(UserGene)
            .join(
                NamespaceContractGene,
                NamespaceContractGene.user_gene_id == UserGene.id,
            )
            .where(
                NamespaceContractGene.contract_id == contract.id,
                NamespaceContractGene.deleted_at.is_(None),
                UserGene.deleted_at.is_(None),
            )
            .order_by(UserGene.slug)
        )
    ).scalars().all()
    return NamespaceContractOut(
        id=contract.id,
        namespace_id=contract.namespace_id,
        user_id=contract.user_id,
        genes=[NamespaceContractGeneRef(id=g.id, slug=g.slug) for g in rows],
        created_at=contract.created_at,
        updated_at=contract.updated_at,
    )


async def _replace_genes(
    db: DB, contract: NamespaceContract, gene_slugs: list[str]
) -> None:
    genes_by_slug = await _atom_genes(db, gene_slugs)
    desired_ids = {g.id for g in genes_by_slug.values()}
    links = (
        await db.execute(
            select(NamespaceContractGene).where(
                NamespaceContractGene.contract_id == contract.id,
                NamespaceContractGene.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    current_ids = {link.user_gene_id for link in links}
    for link in links:
        if link.user_gene_id not in desired_ids:
            link.soft_delete()
    for gene_id in desired_ids - current_ids:
        db.add(NamespaceContractGene(contract_id=contract.id, user_gene_id=gene_id))
    await db.flush()


@router.get(
    "/{namespace_id}/contracts",
    response_model=OffsetPage[NamespaceContractOut],
)
async def list_contracts(
    namespace_id: str,
    db: DB,
    current_user: CurrentUserDep,
    limit: int = 50,
    offset: int = 0,
) -> OffsetPage:
    await _get_namespace(db, namespace_id)
    # v4.0 audit fix: reading the contract ledger requires at least view-level
    # access to the namespace (org or namespace grant).
    await require_permission(
        db,
        current_user.user_id,
        "can_view_workspace",
        namespace_id=namespace_id,
    )
    stmt = (
        select(NamespaceContract)
        .where(
            NamespaceContract.namespace_id == namespace_id,
            NamespaceContract.deleted_at.is_(None),
        )
        .order_by(NamespaceContract.created_at)
    )
    page = await paginate_offset(db, stmt, offset, min(limit, 200))
    items = [await _contract_out(db, c) for c in page.items]
    return OffsetPage(
        items=items,
        offset=page.offset,
        limit=page.limit,
        total=page.total,
    )


@router.post(
    "/{namespace_id}/contracts",
    response_model=NamespaceContractOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_contract(
    namespace_id: str,
    body: NamespaceContractCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> NamespaceContractOut:
    ns = await _get_namespace(db, namespace_id)
    # v4.0 audit fix: granting namespace atoms is a privileged operation —
    # without this gate any authenticated user could self-grant workspace atoms.
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_namespace",
        namespace_id=namespace_id,
    )
    user = await db.get(User, body.user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError(
            "user.not_found",
            "errors.user.not_found",
            f"User '{body.user_id}' not found",
        )
    existing = await db.execute(
        select(NamespaceContract).where(
            NamespaceContract.namespace_id == namespace_id,
            NamespaceContract.user_id == body.user_id,
            NamespaceContract.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "namespace_contract.exists",
            "errors.namespace_contract.exists",
            "Contract already exists for this user in the namespace",
        )
    await _ensure_org_contract(db, organization_id=ns.org_id, user_id=body.user_id)
    contract = NamespaceContract(
        namespace_id=namespace_id,
        user_id=body.user_id,
    )
    db.add(contract)
    await db.flush()
    if body.gene_slugs:
        await _replace_genes(db, contract, body.gene_slugs)
    await db.commit()
    await db.refresh(contract)
    return await _contract_out(db, contract)


@router.patch(
    "/{namespace_id}/contracts/{contract_id}",
    response_model=NamespaceContractOut,
)
async def update_contract(
    namespace_id: str,
    contract_id: str,
    body: NamespaceContractUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> NamespaceContractOut:
    await _get_namespace(db, namespace_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_namespace",
        namespace_id=namespace_id,
    )
    contract = await db.get(NamespaceContract, contract_id)
    if (
        contract is None
        or contract.deleted_at is not None
        or contract.namespace_id != namespace_id
    ):
        raise NotFoundError(
            "namespace_contract.not_found",
            "errors.namespace_contract.not_found",
            f"Contract '{contract_id}' not found",
        )
    if body.gene_slugs is not None:
        await _replace_genes(db, contract, body.gene_slugs)
    await db.commit()
    await db.refresh(contract)
    return await _contract_out(db, contract)


@router.delete(
    "/{namespace_id}/contracts/{contract_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_contract(
    namespace_id: str,
    contract_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> None:
    await _get_namespace(db, namespace_id)
    await require_permission(
        db,
        current_user.user_id,
        "can_manage_namespace",
        namespace_id=namespace_id,
    )
    contract = await db.get(NamespaceContract, contract_id)
    if (
        contract is None
        or contract.deleted_at is not None
        or contract.namespace_id != namespace_id
    ):
        raise NotFoundError(
            "namespace_contract.not_found",
            "errors.namespace_contract.not_found",
            f"Contract '{contract_id}' not found",
        )
    contract.soft_delete()
    await db.commit()
