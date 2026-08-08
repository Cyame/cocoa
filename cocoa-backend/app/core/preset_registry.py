"""Preset registry — in-memory cache of ``BaseClass`` rows.

The registry is loaded at application startup from the database and refreshed
after every CRUD write to ``base_classes``.  It provides a simple
``dict[str, BaseClass]`` lookup by slug plus helpers to resolve per-preset
commands, tools, skills, and check global commands.

``GLOBAL_COMMANDS`` is the fixed list of slash commands available in every
preset (``/read``, ``/list``, ``/write``, ``/archive``).  Per-preset commands
live inside each preset's ``manifest.commands``.

Usage::

    from app.core.preset_registry import registry

    # At startup (inside lifespan):
    async with get_session_factory()() as s:
        await registry.load(s)

    # At runtime:
    preset = registry.get("fox")                       # BaseClass | None
    cmds = registry.get_commands("fox")                # list[str]
    tools = registry.get_tools("fox")                  # list[str]
    skills = registry.get_skills("fox")                # list[str]
    all_presets = registry.list_presets()              # list[BaseClass]
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base_class import BaseClass

# ── Global commands ──────────────────────────────────────────────────────────

GLOBAL_COMMANDS: list[str] = ["/read", "/list", "/write", "/archive"]

# ── Harness control commands (P8) ────────────────────────────────────────────
# Third command category — privileged, available on every Instance,
# routes to the Harness Supervisor rather than the message passage.
# Slash prefix matches the P4 parser output convention.
CONTROL_COMMANDS: list[str] = [
    "/interrupt",
    "/pause",
    "/resume",
    "/status",
    "/snapshot",
]


def is_control_command(cmd: str) -> bool:
    """Return True if *cmd* is a harness control command.

    Case-sensitive match against :data:`CONTROL_COMMANDS`. The slash prefix
    is included — P4's parser outputs ``Directive.cmd`` with the prefix.
    """
    return cmd in CONTROL_COMMANDS


# ── Learning commands (P10) ───────────────────────────────────────────────────
# Fourth command category — operates on entity memory & skill distillation,
# creating new BaseClass rows rather than routing through the message
# passage or the harness supervisor.
LEARNING_COMMANDS: list[str] = [
    "/distill",
    "/consolidate",
    "/reflect",
]


def is_learning_command(cmd: str) -> bool:
    """Return True if *cmd* is a learning command.

    Case-sensitive match against :data:`LEARNING_COMMANDS`. The slash prefix
    is included — P4's parser outputs ``Directive.cmd`` with the prefix.
    Requires an explicit ``@target``; bare learning commands are silently
    dropped, matching the P5 bare-cmd semantics.
    """
    return cmd in LEARNING_COMMANDS


# ── Registry singleton ───────────────────────────────────────────────────────


class PresetRegistry:
    """In-memory cache of all active (non-deleted) ``BaseClass`` rows.

    Thread-safe for reads (``get``, ``get_commands``, ``get_tools``,
    ``get_skills``, ``list_presets``).
    Writes via ``load`` / ``reload`` replace the entire cache atomically.
    """

    def __init__(self) -> None:
        self._cache: dict[str, BaseClass] = {}

    # ── Public API ────────────────────────────────────────────────────────

    async def load(self, session: AsyncSession) -> None:
        """Load all active presets from the database into the in-memory cache.

        Call once at application startup (inside ``lifespan``).
        """
        stmt = select(BaseClass).where(BaseClass.deleted_at.is_(None))
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        self._cache = {row.slug: row for row in rows}

    async def reload(self, session: AsyncSession) -> None:
        """Refresh the cache from the database.

        Call after every CRUD write (create, update, delete) to
        ``base_classes`` so the next lookup sees the new state.
        """
        await self.load(session)

    def get(self, slug: str) -> BaseClass | None:
        """Return the active preset with *slug*, or ``None``."""
        return self._cache.get(slug)

    def get_tools(self, slug: str) -> list[str]:
        """Return the tools list for the preset identified by *slug*.

        Returns an empty list when the preset does not exist or its manifest
        has no ``tools`` key.
        """
        preset = self._cache.get(slug)
        if preset is None or preset.manifest is None:
            return []
        return list(preset.manifest.get("tools", []))

    def get_skills(self, slug: str) -> list[str]:
        """Return the skills list for the preset identified by *slug*.

        Returns an empty list when the preset does not exist or its manifest
        has no ``skills`` key.
        """
        preset = self._cache.get(slug)
        if preset is None or preset.manifest is None:
            return []
        return list(preset.manifest.get("skills", []))

    def get_commands(self, slug: str) -> list[str]:
        """Return the commands list for the preset identified by *slug*.

        Returns an empty list when the preset does not exist or its manifest
        has no ``commands`` key.
        """
        preset = self._cache.get(slug)
        if preset is None or preset.manifest is None:
            return []
        return list(preset.manifest.get("commands", []))

    def list_presets(self) -> list[BaseClass]:
        """Return every cached preset as a list."""
        return list(self._cache.values())

    @staticmethod
    def is_global_command(cmd: str) -> bool:
        """Return ``True`` if *cmd* is a recognised global command.

        The check is case-sensitive and includes the ``/`` prefix matching the
        P4 parser output.
        """
        return cmd in GLOBAL_COMMANDS


# Module-level singleton.
registry = PresetRegistry()
