"""AiGene (L2) — capability packaging (Gene market).

Per docs/prd-v1.md §2.2.3 / §13.6.10: a Gene is a named bundle of
capabilities plus optional SKILL.md content / tool allowlists / scripts /
runtime config patches. 4 kinds (tool-gene / meta-gene / genome /
workflow-gene) map to nodeskclaw's 4-class gene taxonomy.

Cross-references:
- BaseClass (L3) → N:N via ``BaseClass.manifest.installed_gene_slugs[]``.
- CapabilityMarketEntry (L1) → referenced inside ``manifest`` (capability
  list) — the exact field name is left to ``manifest`` JSON shape.
- A ``genome``-kind gene aggregates other genes via the ``gene_slugs`` list.

Soft-delete with partial unique index on ``slug``.
"""

from __future__ import annotations

from enum import Enum

from sqlalchemy import Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class AiGeneKind(str, Enum):
    """4-kind taxonomy from nodeskclaw (carried into Cocoa)."""

    tool_gene = "tool-gene"
    meta_gene = "meta-gene"
    genome = "genome"
    workflow_gene = "workflow-gene"


class AiGene(BaseModel, Base):
    """A named capability bundle (Gene market row).

    See ``docs/prd-v1.md`` §2.2.3 for the full manifest shape. Manifest is a
    JSONB blob with optional ``skill`` / ``tool_allow`` / ``scripts`` /
    ``runtime_config`` keys; ``gene_slugs`` is only meaningful when
    ``kind="genome"`` (it references other AiGene slugs).
    """

    __tablename__ = "ai_genes"
    __table_args__ = (
        Index(
            "uq_ai_genes_slug",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AiGeneKind.tool_gene.value
    )
    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True, default=list
    )
    manifest: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # gene_slugs only used by kind="genome" — denormalized column for
    # quick reverse lookup without parsing manifest JSONB.
    gene_slugs: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True, default=list
    )
    config_override: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} slug={self.slug!r}"
            f" kind={self.kind!r}>"
        )
