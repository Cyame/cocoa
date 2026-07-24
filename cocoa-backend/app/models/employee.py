"""Employee and EmployeePreset models — agent identity and preset templates."""

import enum

from sqlalchemy import Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class EmployeeRank(str, enum.Enum):
    """Rank level of an employee (agent cell). Stored as string, not PG native enum."""

    intern = "intern"
    researcher = "researcher"
    director = "director"


class EmployeePreset(BaseModel, Base):
    """A reusable preset template for employees (灵格)."""

    __tablename__ = "employee_presets"
    __table_args__ = (
        Index(
            "uq_employee_presets_slug",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    manifest: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} slug={self.slug!r}>"


class Employee(BaseModel, Base):
    """An agent cell (细胞) with rank, optional preset, and display properties."""

    __tablename__ = "employees"
    __table_args__ = (
        Index(
            "uq_employees_slug",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    preset_slug: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    rank: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EmployeeRank.intern
    )
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_color: Mapped[str | None] = mapped_column(String(7), nullable=True)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} slug={self.slug!r} rank={self.rank!r}>"
