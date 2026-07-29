"""Slash-protocol Pydantic schemas.

Forward contract to P4's parser — structured object validation only,
NO raw-text parsing.  P4 will translate lines into these objects; P2
just defines the shape.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ContentRef(BaseModel):
    """Reference to content scoped within the cocoa system.

    Attributes:
        scope: Mandatory content scope.
        path: Optional path within the scope (e.g. a file path for
            ``workspace``, a key for ``central_hub``, etc.).
    """

    scope: Literal["workspace", "fornix", "vault", "memory"]
    path: str | None = None

    @field_validator("scope")
    @classmethod
    def scope_must_not_be_none(cls, v: str | None) -> str:
        """Reject explicit ``None`` values — ``scope`` is mandatory."""
        if v is None:
            raise ValueError("scope is mandatory")
        return v


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
    cmd: str
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
