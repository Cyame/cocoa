"""Distillation engine — converts entity memory entries into capabilities.

A DistillationEngine reads an Entity's Memory records and produces a
DistillResult containing capability candidates (pure data, no DB writes —
persistence belongs to the caller).

v4.9.3 炼化 chain (three-role division, documented here as the engine
contract):

- **reap** = Instance memory → capability draft (instance-private)
- **distill** = Entity memory → org-level capability_market entries
  (``created_via="distill"``; each candidate declares ``required_knowledge``
  slugs; carries **no** has_knowledge)
- **promote** = Instance → Entity (回魂/派生)
- **transmute** = Entity → BaseClass (神职)

The AggregatingDistiller is the default heuristic implementation; callers
can swap in other engines (e.g. LLMDistiller) by conforming to the
DistillationEngine Protocol.

P14a adds :class:`LLMDistiller`, an LLM-powered alternative that calls
``LLMClient.complete()`` with a candidate-generation prompt and parses
the JSON response. On ``LLMError`` or invalid JSON, it falls back to
a heuristic manifest dict so the caller never sees an exception.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity
from app.models.memory import Memory, MemoryKind
from app.schemas.learning import AggregatedMemoryCount, DistillRequest

logger = logging.getLogger(__name__)

# Kebab-case command pattern: lowercase start, then letters/digits/hyphens.
_CMD_PATTERN = re.compile(r"^[a-z][a-z0-9-]+$")

# Minimum character length for lesson content to be eligible as prompt source.
_MIN_PROMPT_CHARS = 50

# Maximum length for truncated prompt text (before "...").
_MAX_PROMPT_CHARS = 200

# Maximum number of candidates to extract from memory keys.
_MAX_COMMANDS = 10


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class CapabilityCandidate:
    """One distilled capability candidate (memory → capability_market).

    Mirrors the capability_market row shape: ``name`` / ``type`` /
    ``description`` / ``config_template`` plus the v4.9.3
    ``required_knowledge`` slug declaration (keys == knowledge_entries
    keys == Instance env keys). Candidates never carry has_knowledge —
    real knowledge assets are attached by promote / transmute.
    """

    name: str
    type: str = "skill"
    description: str | None = None
    config_template: dict[str, Any] | None = None
    required_knowledge: list[str] = field(default_factory=list)


@dataclass
class DistillResult:
    """Output from DistillationEngine.distill() — pure data, no DB side effects.

    v4.9.3: the engine computes capability candidates + a gene suggestion
    and aggregated memory counts; callers handle persistence (writing
    capability_market rows, emitting events, etc.).
    """

    capability_candidates: list[CapabilityCandidate]
    gene_suggestion: str | None
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
    DistillResult containing capability candidates. The engine does NOT
    persist anything — that responsibility belongs to the caller.

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


def aggregate_memory_counts(entries: list[Memory]) -> AggregatedMemoryCount:
    """Per-kind memory counts + total for a list of Memory rows."""
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
    return AggregatedMemoryCount(
        experience=kind_counts["experience"],
        lesson=kind_counts["lesson"],
        decision=kind_counts["decision"],
        problem=kind_counts["problem"],
        notepad=kind_counts["notepad"],
        total=sum(kind_counts.values()),
    )


class AggregatingDistiller:
    """Heuristic distillation engine — stateless, no DB writes.

    Algorithm
    ---------
    1. Look up Entity by ID (raise ``DistillationError`` if not found).
    2. Query ``Memory`` for the entity, filtered by kind (optional),
       excluding soft-deleted rows.
    3. Aggregate counts by ``MemoryKind`` → ``AggregatedMemoryCount``.
    4. Extract kebab-case keys from ``lesson`` / ``decision`` entries →
       capability candidates (deduplicated, max 10). Each candidate is
       a ``CapabilityCandidate`` named by its memory key, typed ``skill``,
       described by the truncated entry content, and declaring the key's
       first segment as its ``required_knowledge`` slug.
    5. Count key-prefix frequency across the candidate-source entries
       (``lesson`` / ``decision``, never notepad) → the most frequent
       prefix becomes the ``gene_suggestion`` (the skill domain the
       candidates cluster around).
    6. Notepad mirror keys (``notepad/<plan>/<name>``) are internal
       bookkeeping — never distilled into candidates or the suggestion.
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
        aggregated = aggregate_memory_counts(entries)

        # 4. Kebab-case keys from lesson/decision → capability candidates.
        candidates: list[CapabilityCandidate] = []
        seen_names: set[str] = set()
        for e in entries:
            if e.kind not in (MemoryKind.lesson.value, MemoryKind.decision.value):
                continue
            if not e.key or not _is_kebab_case(e.key) or e.key in seen_names:
                continue
            seen_names.add(e.key)
            prefix = _extract_key_prefix(e.key)
            candidates.append(
                CapabilityCandidate(
                    name=e.key,
                    type="skill",
                    description=_truncate_content(e.content or e.key),
                    required_knowledge=[prefix] if prefix else [],
                )
            )
            if len(candidates) >= _MAX_COMMANDS:
                break

        # 5. Key-prefix frequency among candidate sources (lesson/decision,
        #    excluding notepad) → gene suggestion. The suggestion clusters
        #    around the same entries the candidates came from.
        prefix_counts: dict[str, int] = {}
        for e in entries:
            if e.kind not in (
                MemoryKind.lesson.value,
                MemoryKind.decision.value,
            ) or not e.key:
                continue
            prefix = _extract_key_prefix(e.key)
            if prefix:
                prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
        gene_suggestion = (
            max(prefix_counts, key=prefix_counts.get) if prefix_counts else None
        )

        return DistillResult(
            capability_candidates=candidates,
            gene_suggestion=gene_suggestion,
            aggregated_memory=aggregated,
            source_entity_id=entity_id,
            source_preset_slug=request.source_preset_slug,
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
