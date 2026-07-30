"""NamespaceContract (契印) CRUD — PRD-v3.4."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, NotFoundError
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.models.namespace_contract import NamespaceContract
from app.models.organization import Namespace
from app.models.user import User
from app.schemas.namespace_contract import (
    NamespaceContractCreate,
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
    stmt = (
        select(NamespaceContract)
        .where(
            NamespaceContract.namespace_id == namespace_id,
            NamespaceContract.deleted_at.is_(None),
        )
        .order_by(NamespaceContract.created_at)
    )
    return await paginate_offset(db, stmt, offset, min(limit, 200))


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
) -> NamespaceContract:
    await _get_namespace(db, namespace_id)
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
    contract = NamespaceContract(
        namespace_id=namespace_id,
        user_id=body.user_id,
        role=body.role,
        permissions=body.permissions,
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return contract


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
) -> NamespaceContract:
    await _get_namespace(db, namespace_id)
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
    patch = body.model_dump(exclude_unset=True)
    for field, value in patch.items():
        setattr(contract, field, value)
    await db.commit()
    await db.refresh(contract)
    return contract


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
