"""Authentication schemas.

``CurrentUser`` is the P4-P10 authentication contract: every authenticated
endpoint receives it via ``Depends(get_current_user)``. P4 replaces only the
stub logic inside the dependency — this model stays identical.
"""

from pydantic import BaseModel


class CurrentUser(BaseModel):
    """The authenticated caller of the current request."""

    user_id: str
    is_super_admin: bool
    token: str | None = None
