"""Six built-in agent presets (灵格) shipped with every Cocoa deployment.

Each preset has a Chinese slug (P1 naming), a human-readable name, a semantic
version, and a ``manifest`` dict that conforms to the ``PresetManifest`` schema
defined in ``app/schemas/preset.py``.

P14a upgrade: each manifest now carries a ``provider`` sub-dict describing
which LLMClient to use (4 provider types — see ``app/schemas/llm.py``).
``zong-jian`` (Director) is human-driven and sets ``provider=None`` — it
does not route through any LLM. The ``prompt`` placeholder is now
``"TODO P14a"``; the real system prompt arrives in P14b.

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
            "prompt": "TODO P14a",
            "skills": [],
            "tools": [],
            "commands": ["plan", "decompose", "prioritize"],
            "provider": {
                "type": "openai-compatible",
                "model": "gpt-4o-mini",
                "max_tokens": 2048,
                "temperature": 0.7,
            },
        },
    },
    {
        "slug": "zhu-jin",
        "name": "铸金",
        "version": "1.0.0",
        "manifest": {
            "model": "tbd",
            "prompt": "TODO P14a",
            "skills": [],
            "tools": [],
            "commands": ["execute", "build", "test"],
            "provider": {
                "type": "openai-compatible",
                "model": "claude-3-5-sonnet-latest",  # via anthropic-compatible API
                "max_tokens": 4096,
                "temperature": 0.5,
            },
        },
    },
    {
        "slug": "ling-shi",
        "name": "灵视",
        "version": "1.0.0",
        "manifest": {
            "model": "tbd",
            "prompt": "TODO P14a",
            "skills": [],
            "tools": [],
            "commands": ["analyze", "predict", "review"],
            "provider": {
                "type": "anthropic",
                "model": "claude-3-5-sonnet-latest",
                "max_tokens": 2048,
                "temperature": 0.3,
            },
        },
    },
    {
        "slug": "you-hun",
        "name": "游魂",
        "version": "1.0.0",
        "manifest": {
            "model": "tbd",
            "prompt": "TODO P14a",
            "skills": [],
            "tools": [],
            "commands": ["search", "survey", "report"],
            "provider": {
                "type": "openai-compatible",
                "model": "gpt-4o-mini",
                "max_tokens": 2048,
                "temperature": 0.6,
            },
        },
    },
    {
        "slug": "heng-pan",
        "name": "衡判",
        "version": "1.0.0",
        "manifest": {
            "model": "tbd",
            "prompt": "TODO P14a",
            "skills": [],
            "tools": [],
            "commands": ["review", "approve", "reject"],
            "provider": {
                "type": "anthropic",
                "model": "claude-3-5-haiku-latest",
                "max_tokens": 1024,
                "temperature": 0.4,
            },
        },
    },
    {
        "slug": "zong-jian",
        "name": "总监",
        "version": "1.0.0",
        "manifest": {
            "model": "tbd",
            "prompt": "TODO P14a",
            "skills": [],
            "tools": [],
            "commands": ["approve", "reject", "delegate"],
            "provider": None,  # humans don't need an LLM
        },
    },
]
