"""Memory — append-only per-Entity log (no updated_at)."""

from enum import Enum

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class MemoryKind(str, Enum):
    experience = "experience"
    lesson = "lesson"
    decision = "decision"
    problem = "problem"
    # v4.6: Harness notepad 与 Memory 合一（audit-product-design.md §八）。
    notepad = "notepad"


class Memory(BaseModel, Base):
    """Append-only Entity memory. Never updated; soft-delete only."""

    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_entity_created", "entity_id", "created_at"),
    )

    updated_at = None  # type: ignore[assignment]

    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=False
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
            f"<{cls} {self.id!r} entity={self.entity_id!r}"
            f" kind={self.kind!r}>"
        )
