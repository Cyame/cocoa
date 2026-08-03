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


class NamespaceContractUserRef(BaseModel):
    """Nested user payload — never a UUID wall (v4-3 B3/H6)."""

    id: str
    username: str
    email: str
    nickname: str | None = None


class NamespaceContractAtomRef(BaseModel):
    """One atom entry in the tenant-dashboard contract item."""

    id: str
    slug: str
    name: str


class NamespaceContractMergedOut(BaseModel):
    """v4-3 locked response item for GET /namespaces/{id}/contracts.

    ``inherited_org_atoms`` is the user's OrganizationContract union on the
    namespace's org; the key is omitted entirely (``exclude_unset``) when the
    caller did not request inheritance.
    """

    contract_id: str
    user: NamespaceContractUserRef
    namespace_atoms: list[NamespaceContractAtomRef] = Field(default_factory=list)
    inherited_org_atoms: list[NamespaceContractAtomRef] | None = None
    created_at: datetime


class NamespaceContractAtomsUpdate(BaseModel):
    """v4-3 locked: replace ONLY ``namespace_contract_genes``.

    Provide exactly one of ``atom_slugs`` (catalog-validated slugs) or
    ``gene_ids`` (UserGene ids). The org-inherited layer is never touched.
    """

    atom_slugs: list[str] | None = None
    gene_ids: list[str] | None = None
