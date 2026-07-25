"""JWT token creation/verification and password hashing.

Provides the auth primitives for the P4 auth closure:

- ``create_access_token(user_id, is_super_admin, secret, exp_hours=24)``
- ``decode_token(token, secret)``
- ``hash_password(plain)``
- ``verify_password(plain, hashed)``
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt


def create_access_token(
    user_id: str,
    is_super_admin: bool,
    secret: str,
    exp_hours: int = 24,
) -> str:
    """Create a signed JWT with the given claims.

    Payload::

        {"sub": user_id, "is_super_admin": bool, "exp": utc_timestamp}

    The token is signed with HS256 using *secret*.
    """
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user_id,
        "is_super_admin": is_super_admin,
        "exp": now + timedelta(hours=exp_hours),
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict:
    """Decode and verify a JWT.

    Returns the payload dict on success.

    Raises
    ------
    JWTError
        When the token is expired, malformed, or has an invalid signature.
    """
    return jwt.decode(token, secret, algorithms=["HS256"])


def hash_password(plain: str) -> str:
    """Return the bcrypt hash of *plain*."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return ``True`` when *plain* matches *hashed*."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
