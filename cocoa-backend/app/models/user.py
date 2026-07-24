"""User model — human authentication identity (single-tenant)."""

from sqlalchemy import Boolean, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class User(BaseModel, Base):
    """A human user who can authenticate and interact with the system."""

    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_username",
            "username",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    username: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} username={self.username!r}>"
