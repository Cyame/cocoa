"""BaseClassProviderDefault — per-神职 world Provider + model default (PRD-v3)."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class BaseClassProviderDefault(BaseModel, Base):
    """One default binding per BaseClass (provider_id + model)."""

    __tablename__ = "base_class_provider_defaults"
    __table_args__ = (
        Index(
            "uq_base_class_provider_defaults_base_class",
            "base_class_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    base_class_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("base_classes.id"), nullable=False
    )
    provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organization_providers.id"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} base_class={self.base_class_id!r}"
            f" provider={self.provider_id!r}>"
        )
