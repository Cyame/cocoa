"""InstanceProviderConfig — per-Instance LLM provider override.

P14a D12/D14: each Instance can override the preset's LLM provider config
with a custom API key, base URL, or model selection. Soft-delete + partial
unique index enforce one config per ``(instance_id, provider_type)``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class InstanceProviderConfig(BaseModel, Base):
    """Per-Instance LLM provider configuration.

    Overrides the EmployeePreset's provider config for this specific Instance.
    """

    __tablename__ = "instance_provider_configs"
    __table_args__ = (
        Index(
            "uq_instance_provider_configs_instance_type",
            "instance_id",
            "provider_type",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("instances.id"), nullable=False
    )
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)
    api_key_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_model: Mapped[str] = mapped_column(String(255), nullable=False)
    selected_models: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} instance={self.instance_id!r}"
            f" provider_type={self.provider_type!r}"
            f" default_model={self.default_model!r}>"
        )
