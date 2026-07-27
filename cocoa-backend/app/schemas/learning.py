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
