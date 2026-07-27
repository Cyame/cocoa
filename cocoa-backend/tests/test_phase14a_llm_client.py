"""P14a LLMClient tests — verify 4 provider dispatch works via mocked SDKs."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm.llm_client import LLMClient, LLMResponse


def _patch_sdk_constructors():
    """Patch AsyncOpenAI / AsyncAnthropic so construction does not open real HTTP clients."""
    openai_mock = MagicMock()
    anthropic_mock = MagicMock()
    return (
        patch("app.services.llm.llm_client.AsyncOpenAI", openai_mock),
        patch("app.services.llm.llm_client.AsyncAnthropic", anthropic_mock),
    )


@pytest.mark.asyncio
async def test_openai_compatible_provider() -> None:
    """openai-compatible dispatches to AsyncOpenAI.chat.completions.create."""
    mock_choice = SimpleNamespace(
        message=SimpleNamespace(content="hello from openai"),
        finish_reason="stop",
    )
    mock_usage = SimpleNamespace(prompt_tokens=11, completion_tokens=22)
    mock_resp = SimpleNamespace(
        choices=[mock_choice],
        usage=mock_usage,
        model="gpt-4o-mini-2024-07-18",
    )
    openai_patch, _ = _patch_sdk_constructors()
    with openai_patch as mock_openai_cls:
        mock_openai_instance = MagicMock()
        mock_openai_cls.return_value = mock_openai_instance
        client = LLMClient(provider_type="openai-compatible", api_key="sk-test", base_url=None)

        mock_openai_instance.chat.completions.create = AsyncMock(return_value=mock_resp)
        resp = await client.complete(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=64,
            temperature=0.5,
        )

    assert isinstance(resp, LLMResponse)
    assert resp.content == "hello from openai"
    assert resp.prompt_tokens == 11
    assert resp.completion_tokens == 22
    assert resp.model == "gpt-4o-mini-2024-07-18"
    assert resp.stop_reason == "stop"


@pytest.mark.asyncio
async def test_openai_responses_provider() -> None:
    """openai-responses dispatches to AsyncOpenAI.responses.create; uses input + output_text."""
    mock_usage = SimpleNamespace(input_tokens=7, output_tokens=13)
    mock_resp = SimpleNamespace(
        output_text="hello from responses",
        usage=mock_usage,
        model="gpt-4.1-mini",
    )
    openai_patch, _ = _patch_sdk_constructors()
    with openai_patch as mock_openai_cls:
        mock_openai_instance = MagicMock()
        mock_openai_cls.return_value = mock_openai_instance
        client = LLMClient(provider_type="openai-responses", api_key="sk-test")

        mock_openai_instance.responses.create = AsyncMock(return_value=mock_resp)
        resp = await client.complete(
            messages=[{"role": "user", "content": "hi there"}],
            max_tokens=128,
        )

    assert resp.content == "hello from responses"
    assert resp.prompt_tokens == 7
    assert resp.completion_tokens == 13
    assert resp.model == "gpt-4.1-mini"
    assert resp.stop_reason == "stop"


@pytest.mark.asyncio
async def test_anthropic_provider() -> None:
    """anthropic dispatches to AsyncAnthropic.messages.create; concatenates text blocks."""
    mock_block = SimpleNamespace(text="hello from claude")
    mock_usage = SimpleNamespace(input_tokens=5, output_tokens=9)
    mock_resp = SimpleNamespace(
        content=[mock_block],
        usage=mock_usage,
        model="claude-3-5-sonnet-20241022",
        stop_reason="end_turn",
    )
    _, anthropic_patch = _patch_sdk_constructors()
    with anthropic_patch as mock_anthropic_cls:
        mock_anthropic_instance = MagicMock()
        mock_anthropic_cls.return_value = mock_anthropic_instance
        client = LLMClient(
            provider_type="anthropic",
            api_key="sk-ant-test",
            default_model="claude-3-5-sonnet-20241022",
        )

        mock_anthropic_instance.messages.create = AsyncMock(return_value=mock_resp)
        resp = await client.complete(
            messages=[
                {"role": "system", "content": "you are helpful"},
                {"role": "user", "content": "hi"},
            ],
            max_tokens=256,
        )

    assert resp.content == "hello from claude"
    assert resp.prompt_tokens == 5
    assert resp.completion_tokens == 9
    assert resp.model == "claude-3-5-sonnet-20241022"
    assert resp.stop_reason == "end_turn"
