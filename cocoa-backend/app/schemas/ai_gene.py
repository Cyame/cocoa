"""ai_genes schemas (深海基因)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field


def extract_manifest_capabilities(manifest: dict | None) -> list[dict] | None:
    """Read the inline ``capabilities`` array from an AiGene manifest.

    Shared by ``AiGeneOut`` serialization and frontend edit prefill. Returns
    ``None`` when the manifest is missing or the key is not a list — absent
    capabilities are null, never an empty surrogate (v4.9 A2a contract).
    """
    if not isinstance(manifest, dict):
        return None
    caps = manifest.get("capabilities")
    if not isinstance(caps, list):
        return None
    return caps


class CapabilityInline(BaseModel):
    """Inline capability entry for the AiGene manifest (v4.9 A2a).

    Single serialization schema shared by the ai-genes create/update
    ``capabilities`` field (form checkbox write) and the combine endpoint's
    manifest ``capabilities`` array — the two must stay structurally identical.
    """

    name: str
    type: str | None = None
    description: str | None = None


class AiGeneCreate(BaseModel):
    slug: str
    name: str
    tags: list[str] | None = None
    manifest: dict | None = None
    capabilities: list[CapabilityInline] | None = None
    description: str | None = None
    scope: str = "org"
    organization_id: str | None = None
    namespace_id: str | None = None


class AiGeneUpdate(BaseModel):
    name: str | None = None
    tags: list[str] | None = None
    manifest: dict | None = None
    capabilities: list[CapabilityInline] | None = None
    description: str | None = None


class AiGeneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    tags: list | None = None
    manifest: dict | None = None
    description: str | None = None
    scope: str = "org"
    organization_id: str | None = None
    namespace_id: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def readonly(self) -> bool:
        return self.scope == "system"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def capabilities(self) -> list[dict] | None:
        """Derived array read from ``manifest["capabilities"]`` (not a table)."""
        return extract_manifest_capabilities(self.manifest)


class AiGeneAttachBaseClassRequest(BaseModel):
    base_class_id: str
