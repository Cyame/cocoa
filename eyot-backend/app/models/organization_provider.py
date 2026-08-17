"""OrganizationProvider — world-level LLM provider registry (PRD-v3 / append)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class OrganizationProvider(BaseModel, Base):
    """World registry row: models.dev catalog enablement or custom endpoint."""

    __tablename__ = "organization_providers"
    __table_args__ = (
        Index(
            "uq_organization_providers_org_slug",
            "organization_id",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_organization_providers_org_catalog",
            "organization_id",
            "catalog_provider_id",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND origin = 'catalog'"
            ),
        ),
    )

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False
    )
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    catalog_provider_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    request_format: Mapped[str] = mapped_column(String(20), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_ref: Mapped[str] = mapped_column(Text, nullable=False)
    default_model: Mapped[str] = mapped_column(String(255), nullable=False)
    models_allowlist: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Per-model capability overrides, keyed by model id (display name / extended
    # params / capability toggles). models_allowlist stays a plain id array.
    model_overrides: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    verify_ssl: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    models_endpoint_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="inherit", server_default="inherit"
    )
    models_base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    last_test_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_test_detail: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} slug={self.slug!r}"
            f" origin={self.origin!r}>"
        )
