"""Slash-protocol parser — raw text to structured Turn/Directive.

P4 module: parses raw user input into the P2 ``Turn`` / ``Directive`` /
``ContentRef`` schemas defined in ``app.schemas.slash``.

Grammar (informal)::

    <turn>        := <directive>+
    <directive>   := [<target>] <cmd> [<args>] [<content-ref>]
    <target>      := "@" <entity-name>
    <cmd>         := "/" <name>
    <content-ref> : "@" <scope> [":" <path>]
    scope         := "workspace" | "fornix" | "vault" | "memory"

This is a **pure parser** — it only validates structural syntax, NOT
whether targets or commands exist.  Command validation, target resolution,
and directive execution belong to P5+.
"""

from __future__ import annotations

import re
from typing import Literal

from app.schemas.slash import ContentRef, Directive, Turn

Scope = Literal["workspace", "fornix", "vault", "memory"]

# Regex: @entity-name (alphanumeric + hyphens/underscores) at line start
_RE_TARGET = re.compile(r"^@([a-zA-Z0-9_-]+)\s+")

# Regex: @scope:path where scope is one of the 4 keywords
_RE_CONTENT_REF = re.compile(
    r"@(?P<scope>workspace|fornix|vault|memory)"
    r"(?::(?P<path>\S+))?"
)

# Regex: /command (lowercase-start, alphanumeric + hyphens)
_RE_CMD = re.compile(r"/(?P<cmd>[a-z][a-z0-9-]*)")


def parse_directive(line: str) -> Directive | str:
    """Parse a single line into a ``Directive``, or return the raw line.

    Args:
        line: A single line of user input (may or may not be a directive).

    Returns:
        A ``Directive`` if the line contains a valid ``/cmd``,
        otherwise the original string (to be merged into ``general_text``).
    """
    original = line
    remaining = line

    # 1. Extract optional @target at line start.
    target: str | None = None
    m = _RE_TARGET.match(remaining)
    if m:
        target = m.group(1)
        remaining = remaining[m.end() :]

    # 2. Extract /cmd.
    m = _RE_CMD.search(remaining)
    if not m:
        # No command found — this line is general text.
        return original
    cmd = m.group("cmd")
    remaining = remaining[: m.start()] + remaining[m.end() :]

    # 3. Extract @scope:path content-ref(s).  Take the *last* one (closest
    #    to end-of-line — same grammar as a language that allows one ref per
    #    directive); for simplicity we extract all and keep the last.
    content_ref: ContentRef | None = None
    for m in _RE_CONTENT_REF.finditer(remaining):
        scope: str = m.group("scope")
        path: str | None = m.group("path")
        content_ref = ContentRef(
            scope=scope,  # type: ignore[arg-type]
            path=path,
        )
    if content_ref is not None:
        # Remove content-ref tokens from remaining so they don't end up in args.
        remaining = _RE_CONTENT_REF.sub("", remaining).strip()

    # 4. Remaining text → args (whitespace-split, filter empties).
    args = [a for a in remaining.split() if a]

    return Directive(
        target_entity=target,
        cmd="/" + cmd,
        args=args,
        content_ref=content_ref,
        raw_text=original,
    )


def parse_turn(raw_text: str) -> Turn:
    """Parse raw multi-line user input into a ``Turn``.

    Each non-empty line is parsed via ``parse_directive``.
    Lines that parse into a ``Directive`` go into ``directives``;
    lines that don't are joined with ``\\n`` and placed in ``general_text``.

    Args:
        raw_text: The raw user input, possibly multi-line.

    Returns:
        A ``Turn`` with parsed directives and any unparsed general text.
    """
    lines = raw_text.strip().split("\n")

    directives: list[Directive] = []
    general_parts: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        result = parse_directive(stripped)
        if isinstance(result, Directive):
            directives.append(result)
        else:
            general_parts.append(result)

    general_text = "\n".join(general_parts) if general_parts else None
    return Turn(directives=directives, general_text=general_text)
