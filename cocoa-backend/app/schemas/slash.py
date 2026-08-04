"""Slash-protocol Pydantic schemas.

Forward contract to P4's parser — structured object validation only,
NO raw-text parsing.  P4 will translate lines into these objects; P2
just defines the shape.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

#: Legacy ContentRef scope values accepted on input (parse / read path) and
#: their canonical v4.5 replacements.  New code must only write hub/instance.
_LEGACY_SCOPE_MAP: dict[str, str] = {
    "workspace": "hub",
    "fornix": "hub",
    "vault": "hub",
    "blackboard": "hub",
    "memory": "instance",
}


class ContentRef(BaseModel):
    """Reference to content scoped within the cocoa system.

    Attributes:
        scope: Mandatory content scope — ``hub`` (shared content) or
            ``instance`` (per-agent memory).  Legacy values
            (``workspace``/``fornix``/``vault``/``blackboard`` → ``hub``,
            ``memory`` → ``instance``) are normalized on validation so old
            persisted payloads still construct cleanly.
        path: Optional path within the scope (e.g. a file path for
            ``hub``, a key for ``instance`` memory, etc.).
    """

    scope: Literal["hub", "instance"]
    path: str | None = None

    @field_validator("scope", mode="before")
    @classmethod
    def scope_must_not_be_none(cls, v: str | None) -> str:
        """Reject explicit ``None`` and normalize legacy scope values.

        ``scope`` is mandatory.  Legacy pre-v4.5 strings are mapped to the
        canonical enum so read paths (parsed directives, persisted payloads)
        never carry stale values out of the boundary.
        """
        if v is None:
            raise ValueError("scope is mandatory")
        if isinstance(v, str):
            return _LEGACY_SCOPE_MAP.get(v, v)
        return v  # type: ignore[return-value]  # non-str Literal member rejected below


class Directive(BaseModel):
    """A single directive within a turn — one command issued by the user.

    Attributes:
        target_entity: Optional entity/agent this directive is
            addressed to.
        cmd: The command verb (e.g. ``/read``, ``/write``).
        args: Positional arguments for the command.
        content_ref: Optional content reference attached to the directive.
        raw_text: The original raw text this directive was parsed from
            (populated by P4's parser, empty when built programmatically).
    """

    target_entity: str | None = None
    cmd: str = ""  # empty = chat mention (@slug text) without a slash command
    args: list[str] = Field(default_factory=list)
    content_ref: ContentRef | None = None
    raw_text: str = ""


class Turn(BaseModel):
    """A single turn — a user utterance decomposed into a list of directives.

    Attributes:
        directives: Parsed directives extracted from the turn.
        general_text: Free-form text that doesn't parse into any directive.
    """

    directives: list[Directive] = Field(default_factory=list)
    general_text: str | None = None


class CommandRegistry(BaseModel):
    """Forward contract — shape may change when P4 defines full registry.

    This model carries the list of recognised global commands and optional
    per-preset command overrides.  The final schema and semantics will be
    owned by the P4 slash-parser module.
    """

    global_commands: list[str] = Field(default_factory=list)
    preset_commands: dict[str, list[str]] = Field(default_factory=dict)
