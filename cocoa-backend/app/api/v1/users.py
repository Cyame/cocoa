"""User administration API (PRD-v3-post).

Routes (identity-system / super-admin):
    GET    /api/v1/users
    POST   /api/v1/users
    GET    /api/v1/users/{id}
    PATCH  /api/v1/users/{id}
    DELETE /api/v1/users/{id}
    POST   /api/v1/users/{id}/identity
    PUT    /api/v1/users/{id}/extra-genes
"""

from __future__ import annotations

import secrets
import string

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.identity import (
    ALL_IDENTITY_SLUGS,
    IdentityKey,
    identity_key_from_slug,
    resolve_user_identity,
    sync_identity_pack,
    user_meets_identity,
)
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset
from app.core.security import hash_password
from app.models.user import User
from app.models.user_gene import UserGene, UserUserGene
from app.schemas.users import (
    UserCreate,
    UserCreateOut,
    UserExtraGenesSet,
    UserGeneRef,
    UserIdentitySet,
    UserOut,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["Users"])
add_error_responses(router)


def _random_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def _require_user_admin(db: DB, current_user: CurrentUserDep) -> User:
    actor = await db.get(User, current_user.user_id)
    if actor is None or actor.deleted_at is not None:
        raise NotFoundError(
            "auth.user_not_found",
            "errors.auth.user_not_found",
            "Authenticated user not found",
        )
    if not await user_meets_identity(db, actor, "system"):
        raise ForbiddenError(
            "auth.super_admin_required",
            "errors.auth.super_admin_required",
            "System identity required to manage users",
            details={"user_id": current_user.user_id},
        )
    return actor


async def _get_active_user(db: DB, user_id: str) -> User:
    user = await db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError(
            "auth.user_not_found",
            "errors.auth.user_not_found",
            f"User '{user_id}' not found",
        )
    return user


async def _to_out(db: DB, user: User) -> UserOut:
    rows = (
        await db.execute(
            select(UserUserGene, UserGene)
            .join(UserGene, UserGene.id == UserUserGene.user_gene_id)
            .where(
                UserUserGene.user_id == user.id,
                UserUserGene.deleted_at.is_(None),
                UserGene.deleted_at.is_(None),
            )
            .order_by(UserGene.slug)
        )
    ).all()
    locked: list[UserGeneRef] = []
    extras: list[UserGeneRef] = []
    identity_keys: set[IdentityKey] = set()
    for _link, gene in rows:
        key = identity_key_from_slug(gene.slug)
        ref = UserGeneRef(
            id=gene.id,
            slug=gene.slug,
            name=gene.name,
            locked=key is not None or gene.slug in ALL_IDENTITY_SLUGS,
        )
        if ref.locked:
            if key is not None:
                identity_keys.add(key)
            locked.append(ref)
        else:
            extras.append(ref)
    identity, _, _ = await resolve_user_identity(db, user.id)
    return UserOut(
        id=user.id,
        username=user.username,
        nickname=user.nickname,
        email=user.email,
        is_super_admin=bool(user.is_super_admin),
        identity=identity,
        locked_genes=locked,
        extra_genes=extras,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get("", response_model=OffsetPage[UserOut])
async def list_users(
    db: DB,
    current_user: CurrentUserDep,
    limit: int = 50,
    offset: int = 0,
) -> OffsetPage:
    await _require_user_admin(db, current_user)
    stmt = (
        select(User)
        .where(User.deleted_at.is_(None))
        .order_by(User.username)
    )
    page = await paginate_offset(db, stmt, offset, min(limit, 200))
    items = [await _to_out(db, u) for u in page.items]
    return OffsetPage(
        items=items,
        offset=page.offset,
        limit=page.limit,
        total=page.total,
    )


@router.post("", response_model=UserCreateOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: DB,
    current_user: CurrentUserDep,
) -> UserCreateOut:
    await _require_user_admin(db, current_user)
    existing = await db.execute(
        select(User).where(User.username == body.username, User.deleted_at.is_(None))
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "auth.username_taken",
            "errors.auth.username_taken",
            f"Username '{body.username}' is already taken",
        )
    temporary = _random_password()
    user = User(
        username=body.username,
        nickname=body.nickname,
        email=body.email,
        password_hash=hash_password(temporary),
        is_super_admin=False,
    )
    db.add(user)
    await db.flush()
    await sync_identity_pack(db, user, body.identity)
    await db.commit()
    await db.refresh(user)
    out = await _to_out(db, user)
    return UserCreateOut(**out.model_dump(), temporary_password=temporary)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> UserOut:
    await _require_user_admin(db, current_user)
    user = await _get_active_user(db, user_id)
    return await _to_out(db, user)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    body: UserUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> UserOut:
    await _require_user_admin(db, current_user)
    user = await _get_active_user(db, user_id)
    if body.email is not None:
        user.email = body.email
    if "nickname" in body.model_fields_set:
        user.nickname = body.nickname
    if body.identity is not None:
        await sync_identity_pack(db, user, body.identity)
    await db.commit()
    await db.refresh(user)
    return await _to_out(db, user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> None:
    await _require_user_admin(db, current_user)
    if user_id == current_user.user_id:
        raise ConflictError(
            "auth.cannot_delete_self",
            "errors.auth.cannot_delete_self",
            "Cannot delete your own account",
        )
    user = await _get_active_user(db, user_id)
    user.soft_delete()
    links = (
        await db.execute(
            select(UserUserGene).where(
                UserUserGene.user_id == user_id,
                UserUserGene.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for link in links:
        link.soft_delete()
    await db.commit()


@router.post("/{user_id}/identity", response_model=UserOut)
async def set_user_identity(
    user_id: str,
    body: UserIdentitySet,
    db: DB,
    current_user: CurrentUserDep,
) -> UserOut:
    await _require_user_admin(db, current_user)
    user = await _get_active_user(db, user_id)
    await sync_identity_pack(db, user, body.identity)
    await db.commit()
    await db.refresh(user)
    return await _to_out(db, user)


@router.put("/{user_id}/extra-genes", response_model=UserOut)
async def set_user_extra_genes(
    user_id: str,
    body: UserExtraGenesSet,
    db: DB,
    current_user: CurrentUserDep,
) -> UserOut:
    """Replace extra (non-identity) genes; identity pack stays locked."""
    await _require_user_admin(db, current_user)
    user = await _get_active_user(db, user_id)

    desired_ids = set(body.gene_ids)
    if desired_ids:
        genes = (
            await db.execute(
                select(UserGene).where(
                    UserGene.id.in_(desired_ids),
                    UserGene.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        found = {g.id: g for g in genes}
        missing = desired_ids - set(found)
        if missing:
            raise NotFoundError(
                "user_gene.not_found",
                "errors.user_gene.not_found",
                f"UserGene(s) not found: {', '.join(sorted(missing))}",
            )
        for gene in found.values():
            if gene.slug in ALL_IDENTITY_SLUGS or identity_key_from_slug(gene.slug):
                raise ConflictError(
                    "user_gene.identity_locked",
                    "errors.user_gene.identity_locked",
                    f"Cannot attach identity gene '{gene.slug}' as extra; use set identity",
                )

    rows = (
        await db.execute(
            select(UserUserGene, UserGene)
            .join(UserGene, UserGene.id == UserUserGene.user_gene_id)
            .where(
                UserUserGene.user_id == user.id,
                UserUserGene.deleted_at.is_(None),
                UserGene.deleted_at.is_(None),
            )
        )
    ).all()

    current_extra_ids: set[str] = set()
    for link, gene in rows:
        if gene.slug in ALL_IDENTITY_SLUGS or identity_key_from_slug(gene.slug):
            continue
        current_extra_ids.add(gene.id)
        if gene.id not in desired_ids:
            link.soft_delete()

    for gene_id in desired_ids - current_extra_ids:
        db.add(UserUserGene(user_id=user.id, user_gene_id=gene_id))

    await db.commit()
    await db.refresh(user)
    return await _to_out(db, user)
