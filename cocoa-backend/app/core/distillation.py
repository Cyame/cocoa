"""Distillation engine — converts entity memory entries into preset manifests.

A DistillationEngine reads an entity's Memory records and produces a
DistillResult containing a PresetManifest blueprint. The AggregatingDistiller is
the default heuristic implementation; callers can swap in other engines
(e.g. an LLM-based distiller) by conforming to the DistillationEngine Protocol.

The engine does NOT write to the database — it returns a pure DistillResult
that callers handle persistence for.

P14a adds :class:`LLMDistiller`, an LLM-powered alternative that calls
``LLMClient.complete()`` with a manifest-generation prompt and parses
the JSON response. On ``LLMError`` or invalid JSON, it falls back to
:class:`AggregatingDistiller` so the caller never sees an exception.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base_class import BaseClass
from app.models.entity import Entity
from app.models.memory import Memory, MemoryKind
from app.schemas.learning import AggregatedMemoryCount, DistillRequest, SkillManifestPreview

logger = logging.getLogger(__name__)

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
    handle persistence (creating an BaseClass row, emitting events, etc.).
    """

    new_preset_slug: str
    manifest_preview: SkillManifestPreview
    aggregated_memory: AggregatedMemoryCount
    source_entity_id: str
    source_preset_slug: str | None


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------


class DistillationError(Exception):
    """Recoverable error during distillation (maps to HTTP error responses).

    Attributes:
        code: Machine-readable error code (e.g. ``"entity.not_found"``).
        message_key: i18n message key (e.g. ``"errors.entity.not_found"``).
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

    Implementations read an entity's memory entries and produce a
    DistillResult containing a PresetManifest. The engine does NOT persist
    anything — that responsibility belongs to the caller.

    Usage::

        engine: DistillationEngine = AggregatingDistiller()
        result = await engine.distill(
            entity_id, request=DistillRequest(...), session=session
        )
    """

    async def distill(
        self,
        entity_id: str,
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
    1. Look up Entity by ID (raise ``DistillationError`` if not found).
    2. Query ``Memory`` for the entity, filtered by kind (optional),
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
        entity_id: str,
        *,
        request: DistillRequest,
        session: AsyncSession,
    ) -> DistillResult:
        # 1. Look up entity.
        emp = await session.get(Entity, entity_id)
        if emp is None:
            raise DistillationError(
                code="entity.not_found",
                message_key="errors.entity.not_found",
                message=f"Entity {entity_id!r} not found",
            )

        # 2. Query memory entries.
        q = select(Memory).where(
            Memory.entity_id == entity_id,
            Memory.deleted_at.is_(None),
        )
        if request.memory_kind_filter:
            q = q.where(Memory.kind.in_(request.memory_kind_filter))

        result = await session.execute(q)
        entries: list[Memory] = list(result.scalars().all())

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
            "notepad": 0,
        }
        for e in entries:
            if e.kind in kind_counts:
                kind_counts[e.kind] += 1

        total = sum(kind_counts.values())
        aggregated = AggregatedMemoryCount(
            experience=kind_counts["experience"],
            lesson=kind_counts["lesson"],
            decision=kind_counts["decision"],
            problem=kind_counts["problem"],
            notepad=kind_counts["notepad"],
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

        # 6. Key prefix dedup → skills. v4.6: notepad mirror keys
        #    (``notepad/<plan>/<name>``) are internal bookkeeping, not
        #    distilled skills.
        skills: list[str] = []
        seen_skills: set[str] = set()
        for e in entries:
            if e.kind == MemoryKind.notepad.value:
                continue
            if e.key:
                prefix = _extract_key_prefix(e.key)
                if prefix and prefix not in seen_skills:
                    skills.append(prefix)
                    seen_skills.add(prefix)

        # 7. Model from source preset or "tbd".
        model = "tbd"
        source_preset_slug = request.source_preset_slug
        if source_preset_slug:
            preset_q = select(BaseClass).where(
                BaseClass.slug == source_preset_slug,
                BaseClass.deleted_at.is_(None),
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
            source_entity_id=entity_id,
            source_preset_slug=source_preset_slug,
        )


# ---------------------------------------------------------------------------
# LLM-powered distillation (P14a)
# ---------------------------------------------------------------------------


_LLM_DISTILL_MAX_MEMORIES = 20  # token-budget cap


class LLMDistiller:
    """LLM-powered skill distillation (P14a).

    Asks an :class:`LLMClient` to generate a JSON skill manifest from an
    entity's accumulated memories. On ``LLMError`` or malformed JSON
    response, falls back to a simple heuristic dict so the caller never
    raises — distillation always returns *something* useful.
    """

    def __init__(self, llm_client: Any) -> None:
        self.llm_client = llm_client

    async def distill(
        self,
        entity_id: str,
        *,
        memories: list[dict[str, Any]] | None = None,
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        """Return a skill manifest dict; falls back to heuristic on error.

        The LLM distiller takes pre-fetched ``memories`` rather than
        querying the DB itself. When ``memories`` is None and ``session``
        is provided, the distiller queries the DB.
        """
        mem_list: list[dict[str, Any]]
        if memories is not None:
            mem_list = memories
        elif session is not None:
            mem_list = await self._fetch_memories(entity_id, session)
        else:
            mem_list = []

        if not mem_list:
            logger.warning("LLMDistiller: no memories; returning empty manifest")
            return {"commands": [], "skills": [], "tools": [], "prompt": "", "model": "tbd"}

        prompt = self._build_prompt(mem_list)
        try:
            # Lazy import — llm_client is part of P14a and may not be on
            # the path when this module is imported in isolation.
            from app.services.llm.llm_client import LLMError as _LLMError

            response = await self.llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                temperature=0.3,
            )
            return self._parse_response(response.content)
        except (_LLMError, ValueError) as e:
            logger.warning(
                "LLM distillation failed; falling back to heuristic: %s", e,
            )
            return self._heuristic_manifest(mem_list)

    async def _fetch_memories(
        self,
        entity_id: str,
        session: AsyncSession,
    ) -> list[dict[str, Any]]:
        """Query ``Memory`` rows when no in-memory list was passed."""
        result = await session.execute(
            select(Memory).where(
                Memory.entity_id == entity_id,
                Memory.deleted_at.is_(None),
            )
        )
        entries = list(result.scalars().all())
        return [
            {"kind": e.kind, "key": e.key, "content": e.content or ""}
            for e in entries
        ]

    def _build_prompt(self, memories: list[dict[str, Any]]) -> str:
        mem_text = "\n".join(
            f"- [{m.get('kind', 'experience')}] {m.get('content', '')}"
            for m in memories[:_LLM_DISTILL_MAX_MEMORIES]
        )
        return (
            "Based on these memories from an entity:\n\n"
            f"{mem_text}\n\n"
            "Generate a JSON skill manifest with these fields:\n"
            "- commands: list of kebab-case verbs\n"
            "- skills: list of topics\n"
            "- tools: list of function names\n"
            "- prompt: short system prompt\n"
            "- model: recommended model\n\n"
            "Return ONLY valid JSON (no markdown)."
        )

    def _parse_response(self, content: str) -> dict[str, Any]:
        text = content.strip()
        # Strip markdown ```json fences if present.
        if text.startswith("```"):
            text = "\n".join(line for line in text.split("\n") if not line.startswith("```"))
        return json.loads(text)

    @staticmethod
    def _heuristic_manifest(memories: list[dict[str, Any]]) -> dict[str, Any]:
        """Fallback manifest extracted via simple heuristics.

        Used when the LLM call fails or returns malformed JSON. Mirrors
        the spirit of :class:`AggregatingDistiller` but operates on a
        pre-fetched memory list rather than querying the DB.
        """
        commands: list[str] = []
        seen: set[str] = set()
        skills: list[str] = set()  # type: ignore[assignment]
        longest = ""
        for m in memories:
            kind = m.get("kind") or "experience"
            key = m.get("key") or ""
            content = m.get("content") or ""
            if kind in ("lesson", "decision") and _is_kebab_case(key) and key not in seen:
                commands.append(key)
                seen.add(key)
                if len(commands) >= _MAX_COMMANDS:
                    break
            if key:
                prefix = _extract_key_prefix(key)
                if prefix:
                    skills.add(prefix)
            if kind == "lesson" and len(content) > len(longest):
                longest = content
        return {
            "commands": commands,
            "skills": sorted(skills),
            "tools": [],
            "prompt": _truncate_content(longest) if len(longest) >= _MIN_PROMPT_CHARS else "",
            "model": "tbd",
        }
