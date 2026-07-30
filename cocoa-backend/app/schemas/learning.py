"""Learning Pydantic schemas (P10 Wave 1).

DTOs for the skill-distillation flow: requesting a distill, receiving
aggregated memory counts, memory summaries, manifest previews, and the
final distill result.

These are pure data-transfer schemas — no ORM config, no SQLAlchemy imports.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Pattern: lowercase-start, then any number of lowercase letters, digits, or hyphens.
_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")

# Recognised memory kinds in the system.
_VALID_MEMORY_KINDS = frozenset({"experience", "lesson", "decision", "problem"})


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class DistillRequest(BaseModel):
    """Payload for ``POST /api/v1/learning/distill``.

    Triggers a skill-distillation job: collect memories matching
    ``memory_kind_filter`` from the source entity/preset, extract a
    reusable skill at ``target_skill_slug``, and create a new preset
    (optionally naming it via ``target_preset_name``).

    Attributes:
        memory_kind_filter: Which memory kinds to include (None = all).
            Recognised values: ``experience``, ``lesson``, ``decision``,
            ``problem``.
        target_skill_slug: Slug for the extracted skill.
            Must match ``/^[a-z][a-z0-9-]*$/``.
        source_preset_slug: Source BaseClass slug whose memories to
            mine.  ``None`` means mine the entity's own memories.
        target_preset_name: Human-readable name for the new preset.
            ``None`` lets the system auto-generate one.
    """

    memory_kind_filter: list[str] | None = Field(
        default=None,
        description="Which memory kinds to include (None = all).",
    )
    target_skill_slug: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9-]*$",
        description="Slug for the extracted skill (lowercase, alphanumeric + hyphens).",
    )
    source_preset_slug: str | None = Field(
        default=None,
        description="Source preset slug; None means mine entity's own memories.",
    )
    target_preset_name: str | None = Field(
        default=None,
        description="Human-readable name for the new preset (auto-generated if None).",
    )

    @field_validator("memory_kind_filter")
    @classmethod
    def _validate_memory_kind_filter(cls, v: list[str] | None) -> list[str] | None:
        """Reject unrecognised memory kinds if a filter is supplied."""
        if v is None:
            return v
        for i, kind in enumerate(v):
            if kind not in _VALID_MEMORY_KINDS:
                raise ValueError(
                    f"Invalid memory kind at index {i}: {kind!r}. "
                    f"Must be one of {sorted(_VALID_MEMORY_KINDS)}"
                )
        return v


# ---------------------------------------------------------------------------
# Memory aggregates
# ---------------------------------------------------------------------------


class AggregatedMemoryCount(BaseModel):
    """Count of memories grouped by kind, plus a grand total.

    Attributes:
        experience: Number of ``experience`` memories.
        lesson: Number of ``lesson`` memories.
        decision: Number of ``decision`` memories.
        problem: Number of ``problem`` memories.
        total: Sum of all four counts.
    """

    experience: int = Field(default=0, ge=0)
    lesson: int = Field(default=0, ge=0)
    decision: int = Field(default=0, ge=0)
    problem: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)


class MemorySummaryOut(BaseModel):
    """Snapshot of an entity's memory profile.

    Returned as part of ``DistillResultOut`` and available standalone via
    ``GET /api/v1/learning/memory-summary/{entity_id}`` (P10 Wave 1 Todo 4).

    Attributes:
        entity_id: UUID of the entity.
        aggregated_counts: Per-kind memory counts.
        sample_lessons: Up to 5 recent lesson titles/snippets.
        sample_keys_by_kind: Representative memory keys keyed by kind
            (e.g. ``{"decision": ["key1", "key2"], ...}``).
    """

    entity_id: str
    aggregated_counts: AggregatedMemoryCount
    sample_lessons: list[str] = Field(
        default_factory=list,
        description="Up to 5 recent lesson titles/snippets.",
    )
    sample_keys_by_kind: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Representative memory keys grouped by kind.",
    )

    @field_validator("sample_lessons")
    @classmethod
    def _cap_sample_lessons(cls, v: list[str]) -> list[str]:
        """Enforce the maximum of 5 sample lessons."""
        if len(v) > 5:
            raise ValueError(
                f"sample_lessons must contain at most 5 items; got {len(v)}"
            )
        return v


# ---------------------------------------------------------------------------
# Manifest preview
# ---------------------------------------------------------------------------


class SkillManifestPreview(BaseModel):
    """Preview of the manifest that will be generated for the new preset.

    Mirrors the shape of ``PresetManifest`` from ``app.schemas.preset``
    but uses safe defaults so it can be shown before the distillation
    job completes.

    Attributes:
        model: Default LLM model identifier.
        prompt: System prompt for the distilled preset.
        skills: Names of skills the preset activates.
        tools: Names of tools the preset has access to.
        commands: Per-preset slash commands (without ``/`` prefix).
    """

    model: str = "tbd"
    prompt: str = "TODO P8"
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


class DistillResultOut(BaseModel):
    """Response for ``POST /api/v1/learning/distill``.

    Contains everything needed to confirm a successful distillation:
    the new preset identity, a manifest preview, aggregated memory stats,
    and a trail back to the source entity/preset.

    Attributes:
        new_preset_id: UUID of the freshly created BaseClass.
        new_preset_slug: Slug of the new preset.
        new_preset_name: Human-readable name of the new preset.
        manifest_preview: Preview of the new preset's manifest.
        aggregated_memory: Per-kind memory counts from the source.
        source_entity_id: UUID of the source entity.
        source_preset_slug: Slug of the source preset, or ``None`` if
            entity-own memories were used.
    """

    new_preset_id: str
    new_preset_slug: str
    new_preset_name: str
    manifest_preview: SkillManifestPreview
    aggregated_memory: AggregatedMemoryCount
    source_entity_id: str
    source_preset_slug: str | None = None


# ---------------------------------------------------------------------------
# Phase-15f capability lifecycle (PRD §13.6.3–§13.6.5)
# ---------------------------------------------------------------------------

# Recognised 4 memory kinds — same set as the existing DistillRequest.
_VALID_MEMORY_KINDS_LIFE = frozenset({"experience", "lesson", "decision", "problem"})


class ReapRequest(BaseModel):
    """Payload for ``POST /api/v1/learning/instances/{iid}/reap``.

    Per PRD §13.6.3: distil reusable capabilities from an instance's
    Memory log. The defaults are tuned for the common "reap all
    recent memory" flow.

    Attributes:
        memory_kind_filter: Which memory kinds to consume (None = all 4).
        max_capabilities: Hard cap on the number of capabilities produced.
        snapshot_only: If true, return the preview without writing to DB.
    """

    memory_kind_filter: list[str] | None = Field(
        default=None,
        description="Memory kinds to consume (None = all 4).",
    )
    max_capabilities: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Hard cap on the number of capabilities produced.",
    )
    snapshot_only: bool = Field(
        default=False,
        description="If true, return preview without writing.",
    )

    @field_validator("memory_kind_filter")
    @classmethod
    def _validate_memory_kind_filter(cls, v: list[str] | None) -> list[str] | None:
        """Reject unrecognised memory kinds if a filter is supplied."""
        if v is None:
            return v
        for i, kind in enumerate(v):
            if kind not in _VALID_MEMORY_KINDS_LIFE:
                raise ValueError(
                    f"Invalid memory kind at index {i}: {kind!r}. "
                    f"Must be one of {sorted(_VALID_MEMORY_KINDS_LIFE)}"
                )
        return v


class ReapResultOut(BaseModel):
    """Response for ``POST /api/v1/learning/instances/{iid}/reap``.

    Per PRD §13.6.10.3: reap only writes to the *instance-private* cap
    surface (here via ``runtime_config["reaped_capabilities"]``) and the
    L1 capability_market. The Entity row is untouched
    (``entity_changed: false``).
    """

    status: str = "ok"
    reaped_at: str
    instance_id: str
    memory_consumed: int
    capability_distilled: list[dict]
    capability_market_uploaded: int
    instance_local_added: int
    entity_changed: bool = False


class PromoteRequest(BaseModel):
    """Payload for ``POST /api/v1/learning/entities/{eid}/promote``.

    mode=update (回魂): mutate source Entity + bump migration_hash.
    mode=fork (派生): create a new Entity; source untouched.
    """

    mode: Literal["update", "fork"] = Field(
        default="update",
        description="update=回魂 (mutate source); fork=派生 (new Entity)",
    )
    from_instance_id: str | None = Field(
        default=None,
        description="Source instance; defaults to first active instance.",
    )
    include_prompt_regen: bool = Field(
        default=True,
        description="If true, regen prompt snapshot from caps.",
    )
    snapshot_only: bool = Field(
        default=False,
        description="If true, return preview without writing.",
    )
    # fork-only
    new_entity_name: str | None = Field(
        default=None,
        description="Required when mode=fork — display name for new Entity",
    )
    new_entity_slug: str | None = Field(
        default=None,
        description="Required when mode=fork — slug for new Entity",
    )


class PromoteResultOut(BaseModel):
    """Response for promote (回魂 / 派生)."""

    status: str = "ok"
    mode: str = "update"
    promoted_at: str
    entity_id: str
    entity_promotion_migration_hash: str
    capability_promoted_count: int
    prompt_regenerated: bool
    new_prompt_preview: str
    outdated_instances_count: int
    capability_market_uploaded: int
    new_entity_id: str | None = None


class TransmuteRequest(BaseModel):
    """Payload for ``POST /api/v1/learning/entities/{eid}/distill?action=transmute``.

    Per PRD §13.6.5: snapshot an Entity into a new BaseClass (L3
    神职). The source Entity is NOT mutated — transmute is a
    derivative operation.

    Attributes:
        target_base_class_slug: Slug for the new BaseClass row.
        target_base_class_name: Display name for the new BaseClass row.
        memory_kind_filter: Accepted for API stability; ignored in v1.
        snapshot_only: If true, return preview without writing.
    """

    target_base_class_slug: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9-]*$",
        description="Slug for the new BaseClass (lowercase + hyphens).",
    )
    target_base_class_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Display name for the new BaseClass.",
    )
    memory_kind_filter: list[str] | None = Field(
        default=None,
        description="Accepted for v2 stability; ignored in v1.",
    )
    snapshot_only: bool = Field(
        default=False,
        description="If true, return preview without writing.",
    )


class TransmuteResultOut(BaseModel):
    """Response for transmute — 201 with the new BaseClass identity."""

    new_base_class_id: str
    new_base_class_slug: str
    new_base_class_name: str
    manifest_preview: dict
    source_entity_id: str


class CombineRequest(BaseModel):
    """Payload for ``POST /api/v1/learning/capabilities/combine`` (PRD-v2 unified gene)."""

    capability_names: list[str] = Field(
        ...,
        min_length=1,
        description="Slugs of the L1 capabilities to combine.",
    )
    gene_slug: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9-]*$",
        description="Slug for the new AiGene (lowercase + hyphens).",
    )
    gene_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Display name for the new AiGene.",
    )
    tags: list[str] | None = Field(
        default=None,
        description="Optional free-form tags for filtering.",
    )
    snapshot_only: bool = Field(
        default=False,
        description="If true, return preview without writing.",
    )


class CombineResultOut(BaseModel):
    """Response for combine — 201 with the new AiGene identity."""

    new_gene_id: str
    new_gene_slug: str
    referenced_capabilities: list[str]
    manifest_preview: dict
