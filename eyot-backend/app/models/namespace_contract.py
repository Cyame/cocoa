"""NamespaceContract — 契印 (Namespace ↔ User). PRD-v3.4 / v4.0.

Holds **no role** and no permissions JSONB (dropped in v4.0). The grant is
the set of atomic UserGene FKs via ``namespace_contract_genes``, union-
inherited on top of the OrganizationContract atoms (design §13.2).
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class NamespaceContract(BaseModel, Base):
    """Human seal in a Namespace. Product name: 契印 (only at namespace layer)."""

    __tablename__ = "namespace_contracts"
    __table_args__ = (
        Index(
            "uq_namespace_contracts_ns_user",
            "namespace_id",
            "user_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    namespace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("namespaces.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} ns={self.namespace_id!r} user={self.user_id!r}>"


class NamespaceContractGene(BaseModel, Base):
    """N:N junction NamespaceContract ↔ UserGene (atomic grants)."""

    __tablename__ = "namespace_contract_genes"
    __table_args__ = (
        Index(
            "uq_namespace_contract_genes",
            "contract_id",
            "user_gene_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    contract_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("namespace_contracts.id"), nullable=False
    )
    user_gene_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user_genes.id"), nullable=False
    )
