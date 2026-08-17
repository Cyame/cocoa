"""OrganizationContract (世界契印) — Organization ↔ User grant (v4.0 D12).

Holds **no role**. The grant is the set of atomic UserGene FKs via
``organization_contract_genes``. No active row = the user has not joined
the world = the org is invisible to them. A contract whose effective atom
set is empty is treated as "no access" for business APIs.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class OrganizationContract(BaseModel, Base):
    """Human seal in an Organization. Product name: 世界契印."""

    __tablename__ = "organization_contracts"
    __table_args__ = (
        Index(
            "uq_organization_contracts_org_user",
            "organization_id",
            "user_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    # Audit-only: which frontend pack (编组) the atoms were expanded from.
    source_pack: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} org={self.organization_id!r} user={self.user_id!r}>"


class OrganizationContractGene(BaseModel, Base):
    """N:N junction OrganizationContract ↔ UserGene (atomic grants)."""

    __tablename__ = "organization_contract_genes"
    __table_args__ = (
        Index(
            "uq_organization_contract_genes",
            "contract_id",
            "user_gene_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_organization_contract_genes_gene",
            "user_gene_id",
        ),
    )

    contract_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organization_contracts.id"), nullable=False
    )
    user_gene_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user_genes.id"), nullable=False
    )
