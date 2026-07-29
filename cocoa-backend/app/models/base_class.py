"""BaseClass (L3) — 神职 (AI role template) marketplace.

Per docs/prd-v1.md §13.6.10 / §13.6 / §3.2: a BaseClass is the cross-
workspace reusable AI role template. It composes:

- prompt + commands + provider config
- default capabilities (L1) + default gene refs (L2)
- i18n display name (display_name field is an i18n key, not the actual label)

BaseClass is a NEW table — it does NOT replace the existing
``employee_presets`` table (which P10 distillation still writes to).
A future 15d-rename-2 wave will consolidate them. Until then, both
tables coexist; new code that needs a 神职 reads / writes BaseClass.

Soft-delete with partial unique index on ``slug``.
"""

from __future__ import annotations

from sqlalchemy import Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class BaseClass(BaseModel, Base):
    """A 神职 (AI role template) — cross-workspace reusable.

    ``manifest`` JSONB shape (per PRD §13.6.10 / §13.2):
    {
        "provider_config": {...},        # LLM provider defaults
        "default_model": "gpt-4o-mini",  # default LLM model
        "commands": ["/read", "/write"], # per-preset directive commands
        "default_capabilities": [        # default L1 capability refs
            {"name": "...", "type": "skill"}
        ],
        "default_gene_refs": ["gene-slug-1"],  # default L2 gene refs
        "installed_genes": ["gene-slug-1"],    # alias used by §14b UI
        "system_prompt": "..."                 # optional default prompt
    }
    """

    __tablename__ = "base_classes"
    __table_args__ = (
        Index(
            "uq_base_classes_slug",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True, default=list
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} slug={self.slug!r}>"
