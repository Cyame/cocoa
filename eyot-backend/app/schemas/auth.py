"""Authentication schemas.

``CurrentUser`` is the P4-P10 authentication contract: every authenticated
endpoint receives it via ``Depends(get_current_user)``. P4 replaces only the
stub logic inside the dependency — this model stays identical.

P4 also adds ``RegisterRequest``, ``LoginRequest``, and ``TokenResponse``
for the register/login auth endpoints.
"""

from pydantic import BaseModel, field_validator


class CurrentUser(BaseModel):
    """The authenticated caller of the current request."""

    user_id: str
    is_super_admin: bool
    token: str | None = None


class RegisterRequest(BaseModel):
    """Payload for ``POST /api/v1/auth/register``."""

    username: str
    nickname: str | None = None
    email: str
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("nickname")
    @classmethod
    def nickname_strip(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        return stripped or None


class LoginRequest(BaseModel):
    """Payload for ``POST /api/v1/auth/login``."""

    username: str
    password: str


class OrgIdentityOut(BaseModel):
    """Tenant identity summary for /me (v4-3 B4, display-only, not auth)."""

    organization_id: str
    atoms: list[str]
    display_label: str


class AuthUserOut(BaseModel):
    """Public user fields returned with auth responses /me."""

    id: str
    username: str
    nickname: str | None = None
    email: str
    is_super_admin: bool
    identity: str | None = None
    locked_gene_slugs: list[str] = []
    extra_gene_slugs: list[str] = []
    org_identity: OrgIdentityOut | None = None


class TokenResponse(BaseModel):
    """JWT access token returned on successful register/login."""

    access_token: str
    token_type: str = "bearer"
    user: AuthUserOut | None = None
