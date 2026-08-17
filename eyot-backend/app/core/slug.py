"""Shared kebab-case slug validation (v4.9.4 C4).

Every slug-shaped input across the API (BaseClass / Entity / Organization
create+update, CloneRequest) is validated by this module so the format is
uniform: lowercase letters, digits, and hyphens between segments.

History is NOT back-validated — the pattern gates new inputs only. Historical
rows containing characters outside kebab-case (e.g. underscores) are handled
by query-side escaping (see the Entity rename downstream LIKE check).
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator

# ``^[a-z0-9]+(-[a-z0-9]+)*$`` — kebab-case, at least one char.
SLUG_PATTERN_SOURCE = r"^[a-z0-9]+(-[a-z0-9]+)*$"
SLUG_PATTERN = re.compile(SLUG_PATTERN_SOURCE)


def validate_slug(value: str) -> str:
    """Raise ``ValueError`` unless *value* is kebab-case.

    The clone auto-suffix ``-clone-{8hex}`` is a kebab subset (lowercase hex
    segments) and passes without any special case.
    """
    if not SLUG_PATTERN.match(value):
        raise ValueError(
            "Slug must be kebab-case: lowercase letters, digits, and hyphens "
            "between segments (e.g. 'my-agent-2')"
        )
    return value


KebabSlug = Annotated[str, AfterValidator(validate_slug)]
"""Pydantic field factory — apply to any str slug field."""
