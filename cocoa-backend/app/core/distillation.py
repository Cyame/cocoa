"""Distillation engine — converts employee memory entries into preset manifests.

A DistillationEngine reads an employee's MemoryEntry records and produces a
DistillResult containing a PresetManifest blueprint. The AggregatingDistiller is
the default heuristic implementation; callers can swap in other engines
(e.g. an LLM-based distiller) by conforming to the DistillationEngine Protocol.

The engine does NOT write to the database — it returns a pure DistillResult
that callers handle persistence for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee, EmployeePreset
from app.models.memory import MemoryEntry, MemoryKind
from app.schemas.learning import AggregatedMemoryCount, DistillRequest, SkillManifestPreview

# Kebab-case command pattern: lowercase start, then letters/digits/hyphens.
_CMD_PATTERN = re.compile(r"^[a-z][a-z0-9-]+$")

# Minimum character length for lesson content to be eligible as prompt source.
_MIN_PROMPT_CHARS = 50

# Maximum length for truncated prompt text (before "...").
_MAX_PROMPT_CHARS = 200

# Maximum number of commands to extract from memory keys.
_MAX_COMMANDS = 10


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class DistillResult:
    """Output from DistillationEngine.distill() — pure data, no DB side effects.

    The engine computes the manifest and aggregated memory counts; callers
    handle persistence (creating an EmployeePreset row, emitting events, etc.).
    """

    new_preset_slug: str
    manifest_preview: SkillManifestPreview
    aggregated_memory: AggregatedMemoryCount
    source_employee_id: str
    source_preset_slug: str | None


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------


class DistillationError(Exception):
    """Recoverable error during distillation (maps to HTTP error responses).

    Attributes:
        code: Machine-readable error code (e.g. ``"employee.not_found"``).
        message_key: i18n message key (e.g. ``"errors.employee.not_found"``).
        message: Human-readable error description.
    """

    def __init__(self, code: str, message_key: str, message: str) -> None:
        self.code = code
        self.message_key = message_key
        self.message = message
        super().__init__(message)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class DistillationEngine(Protocol):
    """Interface for distillation engines.

    Implementations read an employee's memory entries and produce a
    DistillResult containing a PresetManifest. The engine does NOT persist
    anything — that responsibility belongs to the caller.

    Usage::

        engine: DistillationEngine = AggregatingDistiller()
        result = await engine.distill(
            employee_id, request=DistillRequest(...), session=session
        )
    """

    async def distill(
        self,
        employee_id: str,
        *,
        request: DistillRequest,
        session: AsyncSession,
    ) -> DistillResult:
        ...


# ---------------------------------------------------------------------------
# Default heuristic implementation
# ---------------------------------------------------------------------------


def _is_kebab_case(value: str) -> bool:
    """Return True if *value* matches the kebab-case command pattern."""
    return bool(_CMD_PATTERN.match(value))


def _truncate_content(text: str, max_chars: int = _MAX_PROMPT_CHARS) -> str:
    """Truncate *text* to *max_chars*, appending ``"..."`` if truncated."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _extract_key_prefix(key: str) -> str:
    """Return the first segment of a hyphen-delimited key."""
    if not key:
        return ""
    return key.split("-")[0]


class AggregatingDistiller:
    """Heuristic distillation engine — stateless, no DB writes.

    Algorithm
    ---------
    1. Look up Employee by ID (raise ``DistillationError`` if not found).
    2. Query ``MemoryEntry`` for the employee, filtered by kind (optional),
       excluding soft-deleted rows.
    3. Aggregate counts by ``MemoryKind`` → ``AggregatedMemoryCount``.
    4. Extract kebab-case keys from ``lesson`` / ``decision`` entries →
       commands list (deduplicated, max 10).
    5. Find the longest lesson content (≥ 50 chars) → truncate to 200 chars
       + ``"..."`` → becomes the prompt.
    6. Extract the first segment of each key (split on ``-``) from all
       entries → deduplicate → skills list.
    7. Model: inherit from ``source_preset.manifest["model"]`` or ``"tbd"``.
    8. Tools: left empty (cannot infer from memory).
    9. Slug: ``{source_preset_slug or 'base'}-skill-{target_skill_slug}``.
    """

    async def distill(
        self,
        employee_id: str,
        *,
        request: DistillRequest,
        session: AsyncSession,
    ) -> DistillResult:
        # 1. Look up employee.
        emp = await session.get(Employee, employee_id)
        if emp is None:
            raise DistillationError(
                code="employee.not_found",
                message_key="errors.employee.not_found",
                message=f"Employee {employee_id!r} not found",
            )

        # 2. Query memory entries.
        q = select(MemoryEntry).where(
            MemoryEntry.employee_id == employee_id,
            MemoryEntry.deleted_at.is_(None),
        )
        if request.memory_kind_filter:
            q = q.where(MemoryEntry.kind.in_(request.memory_kind_filter))

        result = await session.execute(q)
        entries: list[MemoryEntry] = list(result.scalars().all())

        if not entries:
            raise DistillationError(
                code="learning.no_memory",
                message_key="errors.learning.no_memory",
                message="No memory entries for distillation",
            )

        # 3. Aggregate by kind.
        kind_counts: dict[str, int] = {
            "experience": 0,
            "lesson": 0,
            "decision": 0,
            "problem": 0,
        }
        for e in entries:
            if e.kind in kind_counts:
                kind_counts[e.kind] += 1

        total = kind_counts["experience"] + kind_counts["lesson"] + kind_counts["decision"] + kind_counts["problem"]
        aggregated = AggregatedMemoryCount(
            experience=kind_counts["experience"],
            lesson=kind_counts["lesson"],
            decision=kind_counts["decision"],
            problem=kind_counts["problem"],
            total=total,
        )

        # 4. Extract kebab-case keys from lesson/decision → commands.
        commands: list[str] = []
        seen_cmds: set[str] = set()
        for e in entries:
            if e.kind not in (MemoryKind.lesson.value, MemoryKind.decision.value):
                continue
            if e.key and _is_kebab_case(e.key) and e.key not in seen_cmds:
                commands.append(e.key)
                seen_cmds.add(e.key)
                if len(commands) >= _MAX_COMMANDS:
                    break

        # 5. Longest lesson content → prompt.
        prompt = "TODO P8"
        longest_lesson = ""
        for e in entries:
            if e.kind == MemoryKind.lesson.value and e.content:
                if len(e.content) > len(longest_lesson):
                    longest_lesson = e.content
        if len(longest_lesson) >= _MIN_PROMPT_CHARS:
            prompt = _truncate_content(longest_lesson)

        # 6. Key prefix dedup → skills.
        skills: list[str] = []
        seen_skills: set[str] = set()
        for e in entries:
            if e.key:
                prefix = _extract_key_prefix(e.key)
                if prefix and prefix not in seen_skills:
                    skills.append(prefix)
                    seen_skills.add(prefix)

        # 7. Model from source preset or "tbd".
        model = "tbd"
        source_preset_slug = request.source_preset_slug
        if source_preset_slug:
            preset_q = select(EmployeePreset).where(
                EmployeePreset.slug == source_preset_slug,
                EmployeePreset.deleted_at.is_(None),
            )
            preset_result = await session.execute(preset_q)
            source_preset = preset_result.scalar_one_or_none()
            if source_preset is not None and isinstance(source_preset.manifest, dict):
                model = source_preset.manifest.get("model", "tbd")

        # 8. Slug generation.
        base = source_preset_slug or "base"
        new_preset_slug = f"{base}-skill-{request.target_skill_slug}"

        manifest = SkillManifestPreview(
            model=model,
            prompt=prompt,
            skills=skills,
            tools=[],
            commands=commands,
        )

        return DistillResult(
            new_preset_slug=new_preset_slug,
            manifest_preview=manifest,
            aggregated_memory=aggregated,
            source_employee_id=employee_id,
            source_preset_slug=source_preset_slug,
        )
