"""Memory append-log model — employee-indexed immutable records (no UPDATE path)."""

from enum import Enum

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class MemoryKind(str, Enum):
    """Kinds of memory entries.

    Values:
        experience: Hands-on recollection (task, interaction, observation).
        lesson: Generalized insight derived from one or more experiences.
        decision: A choice made by the agent or human, with rationale.
        problem: An encountered obstacle or error, with resolution context.
    """

    experience = "experience"
    lesson = "lesson"
    decision = "decision"
    problem = "problem"


class MemoryEntry(BaseModel, Base):
    """Append-only employee memory log.

    Each entry captures an immutable observation tied to a specific employee.
    Entries are never updated — the model has no ``updated_at`` column.
    Deletion is soft via the inherited ``deleted_at``.

    ``source_instance_id`` is a plain VARCHAR (no FK) because the referenced
    instance may have already been soft-deleted.
    """

    __tablename__ = "memory_entries"
    __table_args__ = (
        Index("ix_memory_entries_employee_created", "employee_id", "created_at"),
    )

    # Override BaseModel.updated_at to remove UPDATE capability.
    updated_at = None  # type: ignore[assignment]

    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    key: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    content: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    source_instance_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, default=None
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} employee={self.employee_id!r}"
            f" kind={self.kind!r} key={self.key!r}>"
        )
