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
    email: str
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    """Payload for ``POST /api/v1/auth/login``."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT access token returned on successful register/login."""

    access_token: str
    token_type: str = "bearer"
