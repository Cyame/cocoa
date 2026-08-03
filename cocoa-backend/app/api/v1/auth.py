"""Authentication endpoints: register, login, and me.

Register/login return a JWT ``TokenResponse`` that includes a ``user`` payload
so the portal can hydrate ``session.user`` (username + is_super_admin).
"""

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUserDep, XOrgIdHeader
from app.core.config import settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from app.core.gene_atoms import ATOM_CATALOG
from app.core.identity import resolve_user_identity
from app.core.openapi import add_error_responses
from app.core.org_scope import resolve_current_org_id
from app.core.permissions import list_grant_slugs
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import (
    AuthUserOut,
    CurrentUser,
    LoginRequest,
    OrgIdentityOut,
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
        nickname=user.nickname,
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
        nickname=body.nickname,
        email=body.email,
        password_hash=hash_password(body.password),
        is_super_admin=is_first_user,
    )
    db.add(user)
    await db.flush()

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


def _display_label(atoms: list[str]) -> str:
    """Map org atoms to a display-only label (v4-3 B4; never auth).

    Priority: owner > operator > editor > viewer.
    """
    if "can_manage_organization" in atoms:
        return "owner"
    if "can_operate_workspace" in atoms:
        return "operator"
    if "can_edit_workspace" in atoms:
        return "editor"
    return "viewer"


async def _org_identity_for(
    db: DB, current_user: CurrentUser, x_organization_id: str | None
) -> OrgIdentityOut | None:
    """Resolve the tenant identity for /me; ``None`` on invalid org / non-member.

    /auth/me is a status endpoint: an invalid ``X-Organization-Id`` header
    (unknown org, malformed id, non-member) must not fail the request — the
    portal renders from ``org_identity``. Super-admins bypass membership and
    report the full atom catalog.
    """
    if x_organization_id is None:
        return None
    try:
        org_id = await resolve_current_org_id(db, current_user.user_id, x_organization_id)
    except (NotFoundError, ForbiddenError):
        return None
    if org_id is None:
        return None
    if current_user.is_super_admin:
        atoms = sorted(ATOM_CATALOG)
    else:
        atoms = sorted(
            await list_grant_slugs(
                db, current_user.user_id, organization_id=org_id
            )
        )
    return OrgIdentityOut(
        organization_id=org_id,
        atoms=atoms,
        display_label=_display_label(atoms),
    )


@router.get("/me", response_model=AuthUserOut)
async def get_me(
    db: DB,
    current_user: CurrentUserDep,
    x_organization_id: XOrgIdHeader = None,
) -> AuthUserOut:
    """Return the authenticated user profile (for session hydration).

    v4-3 B4: when ``X-Organization-Id`` is present and the user holds a valid
    OrganizationContract for that org, the response carries ``org_identity``
    (org-level atom slugs + display label). Invalid / non-member headers
    resolve to ``org_identity: null`` — this endpoint never 4xxes on them.
    """
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
    out = await _user_out(db, user)
    out.org_identity = await _org_identity_for(db, current_user, x_organization_id)
    return out
