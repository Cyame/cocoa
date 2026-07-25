"""Six built-in agent presets (灵格) shipped with every Cocoa deployment.

Each preset has a Chinese slug (P1 naming), a human-readable name, a semantic
version, and a ``manifest`` dict that conforms to the ``PresetManifest`` schema
defined in ``app/schemas/preset.py``.

The ``prompt`` field is set to ``"TODO P8"`` — a skeleton placeholder that
P8 replaces with a real system prompt.  The ``model`` field defaults to
``"tbd"``.

Usage::

    from app.core.builtin_presets import BUILTIN_PRESETS

    for p in BUILTIN_PRESETS:
        print(p["slug"], p["name"])
"""

from __future__ import annotations

# Each preset dict is shaped for direct insertion into the EmployeePreset table:
#   {slug, name, version, manifest}
# where manifest is a JSON-serialisable dict matching PresetManifest.

BUILTIN_PRESETS: list[dict] = [
    {
        "slug": "mi-shi",
        "name": "密士",
        "version": "1.0.0",
        "manifest": {
            "model": "tbd",
            "prompt": "TODO P8",
            "skills": [],
            "tools": [],
            "commands": ["plan", "decompose", "prioritize"],
        },
    },
    {
        "slug": "zhu-jin",
        "name": "铸金",
        "version": "1.0.0",
        "manifest": {
            "model": "tbd",
            "prompt": "TODO P8",
            "skills": [],
            "tools": [],
            "commands": ["execute", "build", "test"],
        },
    },
    {
        "slug": "ling-shi",
        "name": "灵视",
        "version": "1.0.0",
        "manifest": {
            "model": "tbd",
            "prompt": "TODO P8",
            "skills": [],
            "tools": [],
            "commands": ["analyze", "predict", "review"],
        },
    },
    {
        "slug": "you-hun",
        "name": "游魂",
        "version": "1.0.0",
        "manifest": {
            "model": "tbd",
            "prompt": "TODO P8",
            "skills": [],
            "tools": [],
            "commands": ["search", "survey", "report"],
        },
    },
    {
        "slug": "heng-pan",
        "name": "衡判",
        "version": "1.0.0",
        "manifest": {
            "model": "tbd",
            "prompt": "TODO P8",
            "skills": [],
            "tools": [],
            "commands": ["review", "approve", "reject"],
        },
    },
    {
        "slug": "zong-jian",
        "name": "总监",
        "version": "1.0.0",
        "manifest": {
            "model": "tbd",
            "prompt": "TODO P8",
            "skills": [],
            "tools": [],
            "commands": ["approve", "reject", "delegate"],
        },
    },
]
