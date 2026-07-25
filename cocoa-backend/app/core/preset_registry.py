"""Preset registry — in-memory cache of ``EmployeePreset`` rows.

The registry is loaded at application startup from the database and refreshed
after every CRUD write to ``employee_presets``.  It provides a simple
``dict[str, EmployeePreset]`` lookup by slug plus helpers to resolve per-preset
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
    preset = registry.get("mi-shi")                   # EmployeePreset | None
    cmds = registry.get_commands("mi-shi")             # list[str]
    tools = registry.get_tools("mi-shi")               # list[str]
    skills = registry.get_skills("mi-shi")              # list[str]
    all_presets = registry.list_presets()               # list[EmployeePreset]
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import EmployeePreset

# ── Global commands ──────────────────────────────────────────────────────────

GLOBAL_COMMANDS: list[str] = ["read", "list", "write", "archive"]

# ── Registry singleton ───────────────────────────────────────────────────────


class PresetRegistry:
    """In-memory cache of all active (non-deleted) ``EmployeePreset`` rows.

    Thread-safe for reads (``get``, ``get_commands``, ``get_tools``,
    ``get_skills``, ``list_presets``).
    Writes via ``load`` / ``reload`` replace the entire cache atomically.
    """

    def __init__(self) -> None:
        self._cache: dict[str, EmployeePreset] = {}

    # ── Public API ────────────────────────────────────────────────────────

    async def load(self, session: AsyncSession) -> None:
        """Load all active presets from the database into the in-memory cache.

        Call once at application startup (inside ``lifespan``).
        """
        stmt = select(EmployeePreset).where(EmployeePreset.deleted_at.is_(None))
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        self._cache = {row.slug: row for row in rows}

    async def reload(self, session: AsyncSession) -> None:
        """Refresh the cache from the database.

        Call after every CRUD write (create, update, delete) to
        ``employee_presets`` so the next lookup sees the new state.
        """
        await self.load(session)

    def get(self, slug: str) -> EmployeePreset | None:
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

    def list_presets(self) -> list[EmployeePreset]:
        """Return every cached preset as a list."""
        return list(self._cache.values())

    @staticmethod
    def is_global_command(cmd: str) -> bool:
        """Return ``True`` if *cmd* is a recognised global command.

        The check is case-sensitive and does **not** include the ``/`` prefix.
        """
        return cmd in GLOBAL_COMMANDS


# Module-level singleton.
registry = PresetRegistry()
