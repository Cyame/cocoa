"""Learning Pydantic schemas (P10 Wave 1).

DTOs for the skill-distillation flow: requesting a distill, receiving
aggregated memory counts, memory summaries, manifest previews, and the
final distill result.

These are pure data-transfer schemas — no ORM config, no SQLAlchemy imports.
"""

from __future__ import annotations

import re

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
    ``memory_kind_filter`` from the source employee/preset, extract a
    reusable skill at ``target_skill_slug``, and create a new preset
    (optionally naming it via ``target_preset_name``).

    Attributes:
        memory_kind_filter: Which memory kinds to include (None = all).
            Recognised values: ``experience``, ``lesson``, ``decision``,
            ``problem``.
        target_skill_slug: Slug for the extracted skill.
            Must match ``/^[a-z][a-z0-9-]*$/``.
        source_preset_slug: Source EmployeePreset slug whose memories to
            mine.  ``None`` means mine the employee's own memories.
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
        description="Source preset slug; None means mine employee's own memories.",
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
    """Snapshot of an employee's memory profile.

    Returned as part of ``DistillResultOut`` and available standalone via
    ``GET /api/v1/learning/memory-summary/{employee_id}`` (P10 Wave 1 Todo 4).

    Attributes:
        employee_id: UUID of the employee.
        aggregated_counts: Per-kind memory counts.
        sample_lessons: Up to 5 recent lesson titles/snippets.
        sample_keys_by_kind: Representative memory keys keyed by kind
            (e.g. ``{"decision": ["key1", "key2"], ...}``).
    """

    employee_id: str
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
    and a trail back to the source employee/preset.

    Attributes:
        new_preset_id: UUID of the freshly created EmployeePreset.
        new_preset_slug: Slug of the new preset.
        new_preset_name: Human-readable name of the new preset.
        manifest_preview: Preview of the new preset's manifest.
        aggregated_memory: Per-kind memory counts from the source.
        source_employee_id: UUID of the source employee.
        source_preset_slug: Slug of the source preset, or ``None`` if
            employee-own memories were used.
    """

    new_preset_id: str
    new_preset_slug: str
    new_preset_name: str
    manifest_preview: SkillManifestPreview
    aggregated_memory: AggregatedMemoryCount
    source_employee_id: str
    source_preset_slug: str | None = None


# ---------------------------------------------------------------------------
# Phase-15f capability lifecycle (PRD §13.6.3–§13.6.5)
# ---------------------------------------------------------------------------

# Recognised 4 memory kinds — same set as the existing DistillRequest.
_VALID_MEMORY_KINDS_LIFE = frozenset({"experience", "lesson", "decision", "problem"})


class ReapRequest(BaseModel):
    """Payload for ``POST /api/v1/learning/instances/{iid}/reap``.

    Per PRD §13.6.3: distil reusable capabilities from an instance's
    MemoryEntry log. The defaults are tuned for the common "reap all
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
    L1 capability_market. The Employee row is untouched
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

    Per PRD §13.6.4: push an instance's effective capability set into the
    Employee's shared surface (idempotent by capability name) and update
    the migration_hash. Other instances of the same Employee become
    outdated — they must be restarted to pick up the new hash.

    Attributes:
        from_instance_id: Which instance to source caps from. Defaults
            to the first active instance of the Employee.
        include_prompt_regen: If true, regen the prompt snapshot from
            the capability set. v1 keeps this as a flag (no LLM).
        snapshot_only: If true, return preview without writing.
    """

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


class PromoteResultOut(BaseModel):
    """Response for ``POST /api/v1/learning/entities/{eid}/promote``.

    The new migration_hash is the canonical fingerprint of the employee
    going forward — instances whose ``active_hash`` does not match it
    are outdated.
    """

    status: str = "ok"
    promoted_at: str
    entity_id: str
    entity_promotion_migration_hash: str
    capability_promoted_count: int
    prompt_regenerated: bool
    new_prompt_preview: str
    outdated_instances_count: int
    capability_market_uploaded: int


class TransmuteRequest(BaseModel):
    """Payload for ``POST /api/v1/learning/entities/{eid}/distill?action=transmute``.

    Per PRD §13.6.5: snapshot an Employee into a new BaseClass (L3
    神职). The source Employee is NOT mutated — transmute is a
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
    source_employee_id: str


class CombineRequest(BaseModel):
    """Payload for ``POST /api/v1/learning/capabilities/combine``.

    Per PRD §13.6.10.2.2: package N L1 capabilities into a single L2
    Gene (AiGene). The referenced capabilities must exist in the
    capability_market; missing names produce a 404.

    Attributes:
        capability_names: Slugs of the L1 capabilities to combine.
        gene_slug: Slug for the new AiGene row.
        gene_name: Display name for the new AiGene row.
        kind: One of the 4 AiGene kinds.
        tags: Optional free-form tags for filtering.
        snapshot_only: If true, return preview without writing.
    """

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
    kind: str = Field(
        default="tool-gene",
        description="AiGeneKind: tool-gene | meta-gene | genome | workflow-gene.",
    )
    tags: list[str] | None = Field(
        default=None,
        description="Optional free-form tags for filtering.",
    )
    snapshot_only: bool = Field(
        default=False,
        description="If true, return preview without writing.",
    )

    @field_validator("kind")
    @classmethod
    def _validate_kind(cls, v: str) -> str:
        allowed = {"tool-gene", "meta-gene", "genome", "workflow-gene"}
        if v not in allowed:
            raise ValueError(
                f"Invalid kind {v!r}. Must be one of: {sorted(allowed)}"
            )
        return v


class CombineResultOut(BaseModel):
    """Response for combine — 201 with the new AiGene identity."""

    new_gene_id: str
    new_gene_slug: str
    referenced_capabilities: list[str]
    manifest_preview: dict
