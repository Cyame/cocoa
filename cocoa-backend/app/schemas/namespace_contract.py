"""NamespaceContract (契印) schemas — v4.0 (atomic genes, no role)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class NamespaceContractGeneRef(BaseModel):
    id: str
    slug: str


class NamespaceContractCreate(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=36)
    gene_slugs: list[str] = Field(default_factory=list)


class NamespaceContractUpdate(BaseModel):
    """Full replace of the granted atom set when ``gene_slugs`` is provided."""

    gene_slugs: list[str] | None = None


class NamespaceContractOut(BaseModel):
    id: str
    namespace_id: str
    user_id: str
    genes: list[NamespaceContractGeneRef] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
