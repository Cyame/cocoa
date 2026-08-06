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

# Recognised memory kinds in the system (v4.6: notepad 与 Memory 合一).
_VALID_MEMORY_KINDS = frozenset(
    {"experience", "lesson", "decision", "problem", "notepad"}
)


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class DistillRequest(BaseModel):
    """Payload for ``POST /api/v1/learning/entities/{eid}/distill``.

    Triggers a distillation job: collect memories matching
    ``memory_kind_filter`` from the source entity, extract structured
    capability candidates (``capability_candidates``) into the org-level
    capability_market, and suggest a gene slug.

    v4.9.3: distill is the **memory → capability** link of the 炼化 chain
    (reap = Instance draft / promote = Instance→Entity / transmute =
    Entity→BaseClass). The engine selector chooses the extraction
    implementation; ``engine=llm`` degrades to heuristic when no org
    provider is configured (never an error).

    Attributes:
        memory_kind_filter: Which memory kinds to include (None = all).
            Recognised values: ``experience``, ``lesson``, ``decision``,
            ``problem``, ``notepad``.
        target_skill_slug: Slug for the extracted skill.
            Must match ``/^[a-z][a-z0-9-]*$/``.
        source_preset_slug: Source BaseClass slug whose memories to
            mine.  ``None`` means mine the entity's own memories.
        target_preset_name: Kept for API stability; unused in v4.9.3
            (distill no longer creates a preset).
        engine: ``heuristic`` (default) or ``llm``. ``llm`` resolves an
            org provider for the entity's instance; when none is
            available the endpoint degrades to the heuristic engine and
            reports ``engine_used="heuristic"`` + a warning.
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
        description="Kept for API stability; unused in v4.9.3.",
    )
    engine: Literal["heuristic", "llm"] = Field(
        default="heuristic",
        description="Distillation engine: heuristic rules or LLM (degrades on missing provider).",
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
        notepad: Number of ``notepad`` memories (v4.6 Memory∪Notepad).
        total: Sum of all kind counts.
    """

    experience: int = Field(default=0, ge=0)
    lesson: int = Field(default=0, ge=0)
    decision: int = Field(default=0, ge=0)
    problem: int = Field(default=0, ge=0)
    notepad: int = Field(default=0, ge=0)
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


class CapabilityCandidateOut(BaseModel):
    """One distilled capability candidate persisted to the capability_market.

    v4.9.3: distill = Entity memory → capability. Each candidate is a
    market entry with ``created_via="distill"`` (org scope) declaring its
    ``required_knowledge`` slugs (== knowledge_entries keys == Instance
    env keys). It carries **no** has_knowledge — real knowledge assets
    are attached by promote / transmute.

    Attributes:
        id: capability_market row UUID (empty in preview-only paths).
        name: Market slug of the capability.
        type: Capability type (skill / tool / mcp / lsp / command).
        description: Human-readable description.
        config_template: Structured config for the capability (None when
            the heuristic cannot infer one).
        required_knowledge: Slugs the capability needs to function.
        created_via: How the row entered the market (``distill``).
    """

    id: str = ""
    name: str
    type: str = "skill"
    description: str | None = None
    config_template: dict | None = None
    required_knowledge: list[str] = Field(default_factory=list)
    created_via: str = "distill"


class DistillResultOut(BaseModel):
    """Response for ``POST /api/v1/learning/entities/{eid}/distill``.

    v4.9.3: distill writes **capability_market** entries (not a BaseClass).
    The response exposes the created capabilities, the gene suggestion,
    the engine used and any degradation warnings.

    Attributes:
        capability_candidates: Capabilities persisted to the market.
        capability_market_created: Count of new market rows written
            (idempotent upsert by name — repeats are 0).
        gene_suggestion: Suggested AiGene slug packaging the candidates.
        engine_used: ``heuristic`` or ``llm`` (after degradation resolves).
        warnings: Non-blocking notices (e.g.
            ``llm_unavailable_degraded_to_heuristic``).
        aggregated_memory: Per-kind memory counts from the source.
        source_entity_id: UUID of the source entity.
        source_preset_slug: Slug of the source preset, or ``None``.
        new_preset_id / new_preset_slug / new_preset_name /
        manifest_preview: Legacy BaseClass distill fields — kept for the
            historical ``GET /learning/presets/{id}`` compatibility path
            (B4); unused by the new distill endpoint.
    """

    status: str = "ok"
    capability_candidates: list[CapabilityCandidateOut] = Field(
        default_factory=list,
        description="Capabilities distilled into the capability_market.",
    )
    capability_market_created: int = Field(
        default=0,
        description="New capability_market rows written (0 = all names already existed).",
    )
    gene_suggestion: str | None = Field(
        default=None,
        description="Suggested AiGene slug for the distilled capabilities.",
    )
    engine_used: str = Field(
        default="heuristic",
        description="Engine actually used (llm degrades to heuristic).",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-blocking degradation / consistency warnings.",
    )
    aggregated_memory: AggregatedMemoryCount = Field(
        default_factory=AggregatedMemoryCount,
    )
    source_entity_id: str = ""
    source_preset_slug: str | None = None
    # Legacy (B4): historical BaseClass-based distill results via
    # GET /learning/presets/{preset_id}.
    new_preset_id: str | None = None
    new_preset_slug: str | None = None
    new_preset_name: str | None = None
    manifest_preview: SkillManifestPreview | None = None


# ---------------------------------------------------------------------------
# Phase-15f capability lifecycle (PRD §13.6.3–§13.6.5)
# ---------------------------------------------------------------------------

# Recognised 5 memory kinds — same set as the existing DistillRequest.
_VALID_MEMORY_KINDS_LIFE = frozenset(
    {"experience", "lesson", "decision", "problem", "notepad"}
)


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
    # v4.9.3: has-knowledge aggregate — union of the entity's knowledge
    # and the source instance's runtime_config["knowledge"]["env"] keys.
    has_knowledge: list[str] = Field(
        default_factory=list,
        description="Entity has_knowledge after the promote aggregate.",
    )


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
    # v4.9.3: real gene refs (from the Entity's attached genes) and the
    # mounted has-knowledge slug list.
    default_gene_refs: list[str] = Field(
        default_factory=list,
        description="AiGene slugs written to the base_class_ai_genes junction.",
    )
    has_knowledge: list[str] = Field(
        default_factory=list,
        description="has_knowledge mounted from the source Entity.",
    )


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
    # v4.6 §6.4: 组合后按产品选择绑定层（可同时挂 Entity + BaseClass）。
    entity_id: str | None = Field(
        default=None,
        description="Optional Entity to bind the new AiGene to (entity_ai_genes junction).",
    )
    base_class_id: str | None = Field(
        default=None,
        description="Optional BaseClass to bind the new AiGene to (base_class_ai_genes junction).",
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
    entity_id: str | None = None
    base_class_id: str | None = None
