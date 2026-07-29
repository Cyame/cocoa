"""Preset manifest Pydantic schema.

Defines the shape of ``BaseClass.manifest`` JSONB values.
The manifest is a structured blueprint that describes an agent preset's
default model, system prompt, available skills, enabled tools, and
per-preset slash commands.

``model`` defaults to ``"tbd"`` and ``prompt`` to ``"TODO P8"``; both
are placeholder values replaced in later phases (P8 for prompt, P8+ for model).

Usage::

    from app.schemas.preset import PresetManifest

    manifest = PresetManifest(
        model="gpt-4o",
        prompt="You are a helpful assistant.",
        skills=["coding", "reasoning"],
        tools=["web_search", "file_read"],
        commands=["plan", "execute"],
    )
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

# Pattern: lowercase-start, then any number of lowercase letters, digits, or hyphens.
_CMD_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")


class PresetManifest(BaseModel):
    """Structured blueprint for an agent preset (灵格).

    Serialised into the ``BaseClass.manifest`` JSONB column.
    Every field has a safe default so that minimal manifests are valid.

    Attributes:
        model: Default LLM model identifier (e.g. ``"gpt-4o"``).
            Placeholder value ``"tbd"`` until P8+.
        prompt: System prompt for the agent.
            Placeholder value ``"TODO P8"`` until P8.
        skills: Names of skills this preset activates.
        tools: Names of tools this preset has access to.
        commands: Per-preset slash commands (without ``/`` prefix).
            Each item must match ``/^[a-z][a-z0-9-]*$/``.
    """

    model: str = "tbd"
    prompt: str = "TODO P8"
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)

    @field_validator("commands")
    @classmethod
    def _validate_commands(cls, v: list[str]) -> list[str]:
        """Reject commands that don't match ``/^[a-z][a-z0-9-]*$/``."""
        for i, cmd in enumerate(v):
            if not _CMD_PATTERN.match(cmd):
                raise ValueError(
                    f"Invalid command at index {i}: {cmd!r}. "
                    "Commands must match /^[a-z][a-z0-9-]*$/"
                )
        return v
