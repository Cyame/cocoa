"""P14a LLMDistiller tests — LLM-powered distillation engine.

Covers:
1. ``test_llm_distiller_calls_llm`` — mock LLMClient.complete; verify
   the JSON response is parsed into a manifest dict.
2. ``test_llm_distiller_falls_back_to_aggregating_on_json_error`` —
   mock LLMClient.complete to return invalid JSON; verify the
   heuristic fallback manifest is returned.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.core.distillation import LLMDistiller
from app.schemas.learning import DistillRequest
from app.services.llm.llm_client import LLMResponse

# ── 0. Engine selection (v4.9.3) ─────────────────────────────────────────


def test_distill_request_engine_defaults_to_heuristic() -> None:
    """engine is optional and defaults to heuristic."""
    req = DistillRequest(target_skill_slug="test-skill")
    assert req.engine == "heuristic"


def test_distill_request_accepts_llm_engine() -> None:
    """engine='llm' is accepted by the schema."""
    req = DistillRequest(target_skill_slug="test-skill", engine="llm")
    assert req.engine == "llm"


def test_distill_request_rejects_unknown_engine() -> None:
    """engine values outside heuristic|llm are rejected."""
    with pytest.raises(ValidationError):
        DistillRequest(target_skill_slug="test-skill", engine="magic")

# ── 1. Successful LLM call returns parsed manifest dict ─────────────────


@pytest.mark.asyncio
async def test_llm_distiller_calls_llm() -> None:
    """LLMClient.complete() is called; JSON response is parsed into a manifest dict."""
    manifest_json = (
        '{"commands": ["plan", "decompose"], '
        '"skills": ["planning"], '
        '"tools": ["calendar"], '
        '"prompt": "Focus on planning tasks.", '
        '"model": "gpt-4o-mini"}'
    )

    llm_client = MagicMock(name="LLMClient")
    llm_client.complete = AsyncMock(
        return_value=LLMResponse(
            content=manifest_json,
            prompt_tokens=12,
            completion_tokens=34,
            model="gpt-4o-mini",
            stop_reason="stop",
        )
    )

    distiller = LLMDistiller(llm_client)
    result = await distiller.distill(
        "emp-1",
        memories=[
            {"kind": "experience", "key": "exp-1", "content": "Some experience"},
            {"kind": "lesson", "key": "plan-task", "content": "Learn to plan"},
        ],
    )

    assert llm_client.complete.call_count == 1
    assert result["commands"] == ["plan", "decompose"]
    assert result["skills"] == ["planning"]
    assert result["tools"] == ["calendar"]
    assert result["prompt"] == "Focus on planning tasks."
    assert result["model"] == "gpt-4o-mini"


# ── 2. Invalid JSON → heuristic fallback manifest ────────────────────────


@pytest.mark.asyncio
async def test_llm_distiller_falls_back_to_aggregating_on_json_error() -> None:
    """When LLM returns invalid JSON, the distiller falls back to a heuristic manifest."""
    llm_client = MagicMock(name="LLMClient")
    llm_client.complete = AsyncMock(
        return_value=LLMResponse(
            content="not valid json {{{",
            prompt_tokens=5,
            completion_tokens=5,
            model="gpt-4o-mini",
            stop_reason="stop",
        )
    )

    distiller = LLMDistiller(llm_client)
    result = await distiller.distill(
        "emp-2",
        memories=[
            {
                "kind": "lesson",
                "key": "plan-task",
                "content": "Always plan tasks before executing " * 5,
            },
            {
                "kind": "experience",
                "key": "exp-foo",
                "content": "Some experience",
            },
        ],
    )

    assert llm_client.complete.call_count == 1

    # Heuristic fallback extracts kebab-case keys as commands and key
    # prefixes as skills. The exact values are implementation-defined
    # but the manifest must have the expected shape and non-empty lists.
    assert "commands" in result
    assert "skills" in result
    assert "tools" in result
    assert "prompt" in result
    assert "model" in result
    assert isinstance(result["commands"], list)
    assert isinstance(result["skills"], list)
    assert isinstance(result["tools"], list)
    assert "plan-task" in result["commands"]
    assert "exp" in result["skills"]
    assert result["tools"] == []
    assert result["model"] == "tbd"
