"""Authentication endpoints: register and login.

Both endpoints return a JWT ``TokenResponse`` on success.
"""

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import DB
from app.core.config import settings
from app.core.errors import ConflictError, UnauthorizedError
from app.core.openapi import add_error_responses
from app.core.security import create_access_token, hash_password, verify_password
from app.models.office import Membership, MembershipRole, Office
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["Auth"])
add_error_responses(router)


async def _allocate_personal_office_slug(db, base_slug: str) -> str:
    """Return a non-taken slug starting with ``base_slug``.

    Appends ``-2``, ``-3``, ... until a free active slug is found.
    Handles the (rare) case where a deleted-then-recreated user collides
    on the original personal-workspace slug.
    """
    slug = base_slug
    counter = 1
    while True:
        existing = await db.execute(
            select(Office).where(
                Office.slug == slug, Office.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none() is None:
            return slug
        counter += 1
        slug = f"{base_slug}-{counter}"


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, db: DB) -> TokenResponse:
    """Register a new user and return a JWT.

    Username must be unique; duplicate returns 409 Conflict.

    The first user to register against an empty user table is automatically
    promoted to ``is_super_admin=True`` so an empty deployment can be booted
    without manual SQL. Subsequent registrations default to
    ``is_super_admin=False``. See P14b-onboard plan, decision D-perm-2026-07-28.

    P14b-onboard3: every new user is also given a personal workspace
    (``Office`` named ``"{username}'s workspace"``) with an owner
    ``Membership`` so the single-tenant UX lands the user directly into
    ``/offices/{office_id}`` with no separate "create office" step. The
    office id is returned in the ``office_id`` field of the response.
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
    await db.flush()  # need user.id before creating the owner Membership

    # Auto-create the personal workspace so the user lands directly in
    # /offices/{id} after register. Slug collision is handled by the helper.
    personal_slug = await _allocate_personal_office_slug(
        db, f"{body.username}-workspace",
    )
    personal_office = Office(
        name=f"{body.username}'s workspace",
        slug=personal_slug,
    )
    db.add(personal_office)
    await db.flush()  # need office.id before the Membership FK

    owner_membership = Membership(
        office_id=personal_office.id,
        user_id=user.id,
        role=MembershipRole.owner.value,
        posx=0,
        posy=0,
    )
    db.add(owner_membership)
    await db.commit()
    await db.refresh(user)
    await db.refresh(personal_office)

    token = create_access_token(
        user_id=user.id,
        is_super_admin=user.is_super_admin,
        secret=settings.JWT_SECRET,
    )
    return TokenResponse(access_token=token, office_id=personal_office.id)


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

    token = create_access_token(
        user_id=user.id,
        is_super_admin=user.is_super_admin,
        secret=settings.JWT_SECRET,
    )
    return TokenResponse(access_token=token)
