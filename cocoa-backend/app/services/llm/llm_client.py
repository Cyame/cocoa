"""LLMClient — unified LLM call wrapper for 4 provider types.

P14a provider types:
- openai-compatible: any OpenAI-compatible API (OpenAI, Azure, local llama.cpp)
- openai-responses: OpenAI's new /v1/responses endpoint
- anthropic: Anthropic Claude API
- custom: arbitrary OpenAI-compatible URL (e.g., internal LLM gateway)

Each provider dispatches to the right SDK based on LLMProviderConfig.provider_type.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Unified LLM error wrapping openai.APIError / anthropic.APIError."""

    def __init__(self, message_key: str, message: str):
        super().__init__(message)
        self.message_key = message_key
        self.message = message


class LLMResponse:
    """Unified LLM response shape across all 4 providers."""

    def __init__(
        self,
        content: str,
        prompt_tokens: int,
        completion_tokens: int,
        model: str,
        stop_reason: str,
    ):
        self.content = content
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.model = model
        self.stop_reason = stop_reason

    def __repr__(self):
        return (
            f"<LLMResponse model={self.model!r} "
            f"prompt_tokens={self.prompt_tokens} completion_tokens={self.completion_tokens} "
            f"stop_reason={self.stop_reason!r}>"
        )


class LLMClient:
    """Wraps openai + anthropic SDKs. Dispatched by LLMProviderConfig.provider_type."""

    def __init__(
        self,
        provider_type: str,
        api_key: str,
        base_url: str | None = None,
        default_model: str = "gpt-4o-mini",
    ):
        self.provider_type = provider_type
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model

        if provider_type in ("openai-compatible", "openai-responses", "custom"):
            self._openai = AsyncOpenAI(api_key=api_key, base_url=base_url)
            self._anthropic = None
        elif provider_type == "anthropic":
            self._openai = None
            self._anthropic = AsyncAnthropic(api_key=api_key)
        else:
            raise LLMError(
                "errors.llm.unknown_provider",
                f"Unknown provider_type: {provider_type}",
            )

    async def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        model: str | None = None,
    ) -> LLMResponse:
        """Call the configured provider. Returns LLMResponse."""
        model = model or self.default_model
        try:
            if self.provider_type == "anthropic":
                return await self._complete_anthropic(messages, max_tokens, temperature, model)
            elif self.provider_type == "openai-responses":
                return await self._complete_openai_responses(messages, max_tokens, temperature, model)
            else:  # openai-compatible or custom
                return await self._complete_openai_chat(messages, max_tokens, temperature, model)
        except Exception as e:
            logger.exception("LLM call failed", extra={"provider": self.provider_type, "model": model})
            raise LLMError("errors.llm.call_failed", str(e)) from e

    async def _complete_openai_chat(self, messages, max_tokens, temperature, model):
        resp = await self._openai.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        choice = resp.choices[0]
        usage = resp.usage
        return LLMResponse(
            content=choice.message.content or "",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            model=resp.model,
            stop_reason=choice.finish_reason or "stop",
        )

    async def _complete_openai_responses(self, messages, max_tokens, temperature, model):
        """OpenAI's new /v1/responses endpoint (different from /v1/chat/completions)."""
        # Convert messages to input items (simplified: last message is user input)
        user_input = messages[-1].get("content", "") if messages else ""
        resp = await self._openai.responses.create(
            model=model,
            input=user_input,
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        content = resp.output_text if hasattr(resp, "output_text") else ""
        usage = resp.usage
        return LLMResponse(
            content=content,
            prompt_tokens=usage.input_tokens if usage else 0,
            completion_tokens=usage.output_tokens if usage else 0,
            model=resp.model,
            stop_reason="stop",
        )

    async def _complete_anthropic(self, messages, max_tokens, temperature, model):
        """Anthropic Claude API. Convert messages: separate system from user/assistant."""
        system_msg = None
        chat_msgs = []
        for m in messages:
            if m.get("role") == "system":
                system_msg = m["content"]
            else:
                chat_msgs.append({"role": m["role"], "content": m["content"]})
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": chat_msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_msg:
            kwargs["system"] = system_msg
        resp = await self._anthropic.messages.create(**kwargs)
        content = ""
        for block in resp.content:
            if hasattr(block, "text"):
                content += block.text
        usage = resp.usage
        return LLMResponse(
            content=content,
            prompt_tokens=usage.input_tokens if usage else 0,
            completion_tokens=usage.output_tokens if usage else 0,
            model=resp.model,
            stop_reason=resp.stop_reason or "end_turn",
        )


def make_client_from_env(provider_type: str, default_model: str = "gpt-4o-mini") -> LLMClient:
    """Helper: build an LLMClient using env var for API key."""
    api_key_env = {
        "openai-compatible": "OPENAI_API_KEY",
        "openai-responses": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "custom": "CUSTOM_LLM_API_KEY",
    }.get(provider_type, "OPENAI_API_KEY")
    api_key = os.environ.get(api_key_env, "")
    base_url = os.environ.get("OPENAI_BASE_URL") if provider_type in ("openai-compatible", "custom") else None
    return LLMClient(
        provider_type=provider_type,
        api_key=api_key,
        base_url=base_url,
        default_model=default_model,
    )
