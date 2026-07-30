"""Authentication endpoints: register, login, and me.

Register/login return a JWT ``TokenResponse`` that includes a ``user`` payload
so the portal can hydrate ``session.user`` (username + is_super_admin).
"""

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUserDep
from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, UnauthorizedError
from app.core.identity import resolve_user_identity, sync_identity_pack
from app.core.openapi import add_error_responses
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import (
    AuthUserOut,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["Auth"])
add_error_responses(router)


async def _user_out(db: DB, user: User) -> AuthUserOut:
    identity, locked, extras = await resolve_user_identity(db, user.id)
    return AuthUserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        is_super_admin=bool(user.is_super_admin),
        identity=identity,
        locked_gene_slugs=locked,
        extra_gene_slugs=extras,
    )


async def _token_for(db: DB, user: User) -> TokenResponse:
    token = create_access_token(
        user_id=user.id,
        is_super_admin=user.is_super_admin,
        secret=settings.JWT_SECRET,
    )
    return TokenResponse(access_token=token, user=await _user_out(db, user))


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, db: DB) -> TokenResponse:
    """Register a new user and return a JWT.

    Username must be unique; duplicate returns 409 Conflict.

    The first user to register against an empty user table is automatically
    promoted to ``is_super_admin=True`` so an empty deployment can be booted
    without manual SQL. Subsequent registrations default to
    ``is_super_admin=False``. See P14b-onboard plan, decision D-perm-2026-07-28.
    """
    existing = await db.execute(
        select(User).where(User.username == body.username, User.deleted_at.is_(None))
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            "auth.username_taken",
            "errors.auth.username_taken",
            f"Username '{body.username}' is already taken",
        )

    user_count = (
        await db.execute(
            select(func.count(User.id)).where(User.deleted_at.is_(None))
        )
    ).scalar() or 0
    is_first_user = user_count == 0

    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        is_super_admin=is_first_user,
    )
    db.add(user)
    await db.flush()

    # First registrant receives identity-system pack (PRD-v3-post).
    if is_first_user:
        await sync_identity_pack(db, user, "system")
    else:
        await sync_identity_pack(db, user, "member")

    await db.commit()
    await db.refresh(user)
    return await _token_for(db, user)


@router.post("/login", status_code=200)
async def login(body: LoginRequest, db: DB) -> TokenResponse:
    """Authenticate with username and password, returning a JWT.

    Invalid credentials return 401 Unauthorized.
    """
    result = await db.execute(
        select(User).where(User.username == body.username, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise UnauthorizedError(
            "auth.invalid_credentials",
            "errors.auth.invalid_credentials",
            "Invalid username or password",
        )

    return await _token_for(db, user)


@router.get("/me", response_model=AuthUserOut)
async def get_me(db: DB, current_user: CurrentUserDep) -> AuthUserOut:
    """Return the authenticated user profile (for session hydration)."""
    result = await db.execute(
        select(User).where(
            User.id == current_user.user_id,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError(
            "auth.user_not_found",
            "errors.auth.user_not_found",
            "Authenticated user not found",
        )
    return await _user_out(db, user)
