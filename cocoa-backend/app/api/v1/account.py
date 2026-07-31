"""Self-service account API (PRD-v3-post).

Routes:
    GET   /api/v1/account
    PATCH /api/v1/account
    POST  /api/v1/account/password
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep
from app.core.errors import NotFoundError, UnauthorizedError
from app.core.identity import (
    ALL_IDENTITY_SLUGS,
    identity_key_from_slug,
    resolve_user_identity,
)
from app.core.openapi import add_error_responses
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.models.user_gene import UserGene, UserUserGene
from app.schemas.users import (
    AccountOut,
    AccountPasswordChange,
    AccountUpdate,
    UserGeneRef,
)

router = APIRouter(prefix="/account", tags=["Account"])
add_error_responses(router)


async def _current_db_user(db: DB, current_user: CurrentUserDep) -> User:
    user = await db.get(User, current_user.user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError(
            "auth.user_not_found",
            "errors.auth.user_not_found",
            "Authenticated user not found",
        )
    return user


async def _to_account(db: DB, user: User) -> AccountOut:
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
    for _link, gene in rows:
        key = identity_key_from_slug(gene.slug)
        ref = UserGeneRef(
            id=gene.id,
            slug=gene.slug,
            name=gene.name,
            locked=key is not None or gene.slug in ALL_IDENTITY_SLUGS,
        )
        if ref.locked:
            locked.append(ref)
        else:
            extras.append(ref)
    identity, _, _ = await resolve_user_identity(db, user.id)
    return AccountOut(
        id=user.id,
        username=user.username,
        nickname=user.nickname,
        email=user.email,
        is_super_admin=bool(user.is_super_admin),
        identity=identity,
        locked_genes=locked,
        extra_genes=extras,
    )


@router.get("", response_model=AccountOut)
async def get_account(db: DB, current_user: CurrentUserDep) -> AccountOut:
    user = await _current_db_user(db, current_user)
    return await _to_account(db, user)


@router.patch("", response_model=AccountOut)
async def update_account(
    body: AccountUpdate,
    db: DB,
    current_user: CurrentUserDep,
) -> AccountOut:
    user = await _current_db_user(db, current_user)
    if body.email is not None:
        user.email = body.email
    if "nickname" in body.model_fields_set:
        user.nickname = body.nickname
    await db.commit()
    await db.refresh(user)
    return await _to_account(db, user)


@router.post("/password", status_code=204)
async def change_password(
    body: AccountPasswordChange,
    db: DB,
    current_user: CurrentUserDep,
) -> None:
    user = await _current_db_user(db, current_user)
    if not verify_password(body.current_password, user.password_hash):
        raise UnauthorizedError(
            "auth.invalid_credentials",
            "errors.auth.invalid_credentials",
            "Current password is incorrect",
        )
    user.password_hash = hash_password(body.new_password)
    await db.commit()
