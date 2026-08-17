"""Slash-protocol parser — raw text to structured Turn/Directive.

P4 module: parses raw user input into the P2 ``Turn`` / ``Directive`` /
``ContentRef`` schemas defined in ``app.schemas.slash``.

Grammar (informal)::

    <turn>        := <directive>+
    <directive>   := [<target>] <cmd> [<args>] [<content-ref>]
    <target>      := "@" <entity-name>
    <cmd>         := "/" <name>
    <content-ref> : "@" <scope> [":" <path>]
    scope         := "hub" | "instance"

Legacy content-ref scopes (``workspace`` | ``fornix`` | ``vault`` |
``blackboard`` | ``memory``) are still *accepted* in input text so existing
messages don't break, but the parsed ``scope`` is always normalized to the
canonical enum — ``hub`` for hub-scoped storage, ``instance`` for memory.

This is a **pure parser** — it only validates structural syntax, NOT
whether targets or commands exist.  Command validation, target resolution,
and directive execution belong to P5+.
"""

from __future__ import annotations

import re
from typing import Literal

from app.schemas.slash import ContentRef, Directive, Turn

Scope = Literal["hub", "instance"]

#: Legacy → canonical scope map (H7).  Keep in sync with
#: ``app.schemas.slash._LEGACY_SCOPE_MAP``.
_SCOPE_NORMALIZE: dict[str, str] = {
    "workspace": "hub",
    "fornix": "hub",
    "vault": "hub",
    "blackboard": "hub",
    "memory": "instance",
}


def normalize_scope(scope: str) -> str:
    """Map a legacy ContentRef scope string to the v4.5 canonical enum.

    ``workspace``/``fornix``/``vault``/``blackboard`` → ``hub``,
    ``memory`` → ``instance``; new values (``hub``/``instance``) and any
    unknown strings pass through unchanged.
    """
    return _SCOPE_NORMALIZE.get(scope, scope)


# Regex: @entity-name (alphanumeric + hyphens/underscores) at line start.
# Trailing whitespace OR end-of-line (bare ``@slug`` chat mention).
_RE_TARGET = re.compile(r"^@([a-zA-Z0-9_-]+)(?:\s+|$)")

# Regex: @scope:path where scope is a canonical (hub|instance) or legacy
# (workspace|fornix|vault|memory) keyword — legacy values are normalized by
# ``normalize_scope`` after capture.
_RE_CONTENT_REF = re.compile(
    r"@(?P<scope>hub|instance|workspace|fornix|vault|memory)"
    r"(?::(?P<path>\S+))?"
)

# Regex: /command (lowercase-start, alphanumeric + hyphens)
_RE_CMD = re.compile(r"/(?P<cmd>[a-z][a-z0-9-]*)")

# Inline @slug tokens (for same-line multi-mention chat expansion).
_RE_AT_TOKEN = re.compile(r"@([a-zA-Z0-9_-]+)")
# Both canonical and legacy scopes — legacy values still appear in inbound
# text and must be excluded from @slug mention expansion.
_CONTENT_REF_SCOPES = frozenset(
    {"hub", "instance", "workspace", "fornix", "vault", "memory"}
)


def expand_inline_chat_mentions(raw: str) -> list[Directive] | None:
    """Expand ``@a hi @b bye`` (no slash cmds) into one Directive per @slug.

    Returns ``None`` when the line should stay a single parse_directive result
    (zero/one mention, or any ``/cmd`` present).
    """
    if _RE_CMD.search(raw):
        return None
    matches: list[re.Match[str]] = []
    for m in _RE_AT_TOKEN.finditer(raw):
        slug = m.group(1)
        if slug in _CONTENT_REF_SCOPES:
            continue
        if m.start() > 0 and not raw[m.start() - 1].isspace():
            continue
        matches.append(m)
    if len(matches) <= 1:
        return None
    out: list[Directive] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        body = raw[start:end].strip()
        args = [a for a in body.split() if a]
        segment = raw[m.start() : end].strip()
        out.append(
            Directive(
                target_entity=m.group(1),
                cmd="",
                args=args,
                content_ref=None,
                raw_text=segment,
            )
        )
    return out


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

    # 2. Extract /cmd.  PRD-v3.4.1: bare ``@slug message`` (no /cmd) is a
    #    chat mention directive with empty cmd — Composer multi-target chat.
    m = _RE_CMD.search(remaining)
    if not m:
        if target is not None:
            args = [a for a in remaining.split() if a]
            return Directive(
                target_entity=target,
                cmd="",
                args=args,
                content_ref=None,
                raw_text=original,
            )
        return original
    cmd = m.group("cmd")
    remaining = remaining[: m.start()] + remaining[m.end() :]

    # 3. Extract @scope:path content-ref(s).  Take the *last* one (closest
    #    to end-of-line — same grammar as a language that allows one ref per
    #    directive); for simplicity we extract all and keep the last.
    content_ref: ContentRef | None = None
    for m in _RE_CONTENT_REF.finditer(remaining):
        scope: str = normalize_scope(m.group("scope"))
        path: str | None = m.group("path")
        content_ref = ContentRef(
            scope=scope,
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
        expanded = expand_inline_chat_mentions(stripped)
        if expanded is not None:
            directives.extend(expanded)
            continue
        result = parse_directive(stripped)
        if isinstance(result, Directive):
            directives.append(result)
        else:
            general_parts.append(result)

    general_text = "\n".join(general_parts) if general_parts else None
    return Turn(directives=directives, general_text=general_text)
