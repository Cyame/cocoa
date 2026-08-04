"""User administration API (PRD-v3-post).

Routes (identity-system / super-admin):
    GET    /api/v1/users
    POST   /api/v1/users
    GET    /api/v1/users/search     (v4-3 D14: org member-manager search)
    GET    /api/v1/users/{id}
    PATCH  /api/v1/users/{id}
    DELETE /api/v1/users/{id}
    POST   /api/v1/users/{id}/identity
    PUT    /api/v1/users/{id}/extra-genes
"""

from __future__ import annotations

import secrets
import string

from fastapi import APIRouter, Query, status
from sqlalchemy import or_, select

from app.api.deps import DB, CurrentUserDep, XOrgIdHeader
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.identity import resolve_user_identity
from app.core.openapi import add_error_responses
from app.core.org_scope import resolve_current_org_id
from app.core.pagination import OffsetPage, paginate_offset
from app.core.permissions import require_permission
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
    UserSearchOut,
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
    if not actor.is_super_admin:
        raise ForbiddenError(
            "auth.super_admin_required",
            "errors.auth.super_admin_required",
            "Super-admin privileges required to manage users",
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
    """Admin view: identity derived from flag; global extra links are legacy
    platform tooling (tenant grants live on Contracts since v4.0)."""
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
    extras = [
        UserGeneRef(id=gene.id, slug=gene.slug, name=gene.name, locked=False)
        for _link, gene in rows
    ]
    identity, _, _ = await resolve_user_identity(db, user.id)
    return UserOut(
        id=user.id,
        username=user.username,
        nickname=user.nickname,
        email=user.email,
        is_super_admin=bool(user.is_super_admin),
        identity=identity,
        locked_genes=[],
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


@router.get("/search", response_model=OffsetPage[UserSearchOut])
async def search_users(
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
    q: str | None = Query(default=None, max_length=255),
    limit: int = 10,
    offset: int = 0,
) -> OffsetPage:
    """v4-3 D14: search existing users by username/email prefix.

    Permission: ``can_manage_org_members`` on the current org (resolved via
    ``X-Organization-Id`` header + :func:`resolve_current_org_id`) OR
    super-admin. No valid org context and not super-admin → 403. Response is
    slim (``UserSearchOut``) — no password_hash / identity / gene data.

    ``q`` empty or missing → empty result (guards against cross-platform
    PII enumeration; the portal only calls with a non-empty prefix). ``q``
    present → case-insensitive prefix match (ILIKE) on username OR email;
    ``%`` / ``_`` / ``\\`` are escaped and treated literally.
    ``limit`` is clamped to [1, 50] (default 10).
    """
    org_id = await resolve_current_org_id(
        db, current_user.user_id, x_organization_id
    )
    if not current_user.is_super_admin:
        if org_id is None:
            raise ForbiddenError(
                "organization.context_required",
                "errors.organization.context_required",
                "Organization context is required (X-Organization-Id or a single org contract)",
            )
        await require_permission(
            db,
            current_user.user_id,
            "can_manage_org_members",
            organization_id=org_id,
        )

    limit = min(max(limit, 1), 50)
    offset = max(offset, 0)
    needle = q.strip() if q is not None else ""
    if not needle:
        # No prefix → nothing to search. Returning an empty page (rather
        # than "most recent users") prevents any holder of
        # can_manage_org_members from enumerating platform-wide PII.
        return OffsetPage(items=[], offset=offset, limit=limit, total=0)
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"{escaped}%"
    stmt = (
        select(User)
        .where(User.deleted_at.is_(None))
        .where(
            or_(
                User.username.ilike(pattern, escape="\\"),
                User.email.ilike(pattern, escape="\\"),
            )
        )
        .order_by(User.username, User.id)
    )
    page = await paginate_offset(db, stmt, offset, limit)
    items = [
        UserSearchOut(
            id=u.id, username=u.username, email=u.email, nickname=u.nickname
        )
        for u in page.items
    ]
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
        is_super_admin=body.identity == "system",
    )
    db.add(user)
    await db.flush()
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
        user.is_super_admin = body.identity == "system"
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
    """Set platform identity. v4.0: only ``system`` is meaningful (maps to
    ``is_super_admin``); any other value clears the flag. Tenant grants are
    managed via Contracts, not identity packs."""
    await _require_user_admin(db, current_user)
    user = await _get_active_user(db, user_id)
    user.is_super_admin = body.identity == "system"
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
    """Replace globally-attached genes (legacy platform tooling only —
    tenant grants are Contract-based since v4.0)."""
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
        current_extra_ids.add(gene.id)
        if gene.id not in desired_ids:
            link.soft_delete()

    for gene_id in desired_ids - current_extra_ids:
        db.add(UserUserGene(user_id=user.id, user_gene_id=gene_id))

    await db.commit()
    await db.refresh(user)
    return await _to_out(db, user)
