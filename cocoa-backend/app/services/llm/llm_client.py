"""LLMClient — unified LLM call wrapper.

Supports request_format mapping:
- completion → OpenAI chat.completions
- response → OpenAI responses.create
- anthropic → Anthropic messages.create
- gemini → Google Generative Language generateContent (httpx)

Also accepts legacy provider_type values (openai-compatible, etc.).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
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
    """Unified LLM response shape across providers."""

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
            f"prompt_tokens={self.prompt_tokens} "
            f"completion_tokens={self.completion_tokens} "
            f"stop_reason={self.stop_reason!r}>"
        )


_LEGACY_TO_FORMAT: dict[str, str] = {
    "openai-compatible": "completion",
    "openai-responses": "response",
    "anthropic": "anthropic",
    "custom": "completion",
    "gemini": "gemini",
}


from dataclasses import dataclass
from typing import Any, AsyncIterator


@dataclass(frozen=True, slots=True)
class TokenChunk:
    """One streamed token (P14b / PRD-v3.4.1)."""

    token: str
    finish_reason: str | None = None


class LLMClient:
    """Wraps openai + anthropic + gemini. Dispatched by request_format / provider_type."""

    def __init__(
        self,
        provider_type: str,
        api_key: str,
        base_url: str | None = None,
        default_model: str = "gpt-4o-mini",
        *,
        verify_ssl: bool = True,
        request_format: str | None = None,
    ):
        self.provider_type = provider_type
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model
        self.verify_ssl = verify_ssl
        self.request_format = request_format or _LEGACY_TO_FORMAT.get(
            provider_type, "completion"
        )

        self._openai: AsyncOpenAI | None = None
        self._anthropic: AsyncAnthropic | None = None

        if self.request_format in ("completion", "response"):
            http_client = httpx.AsyncClient(verify=verify_ssl)
            self._openai = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                http_client=http_client,
            )
        elif self.request_format == "anthropic":
            http_client = httpx.AsyncClient(verify=verify_ssl)
            kwargs: dict[str, Any] = {
                "api_key": api_key,
                "http_client": http_client,
            }
            if base_url:
                kwargs["base_url"] = base_url
            self._anthropic = AsyncAnthropic(**kwargs)
        elif self.request_format == "gemini":
            pass  # httpx used per-call
        else:
            raise LLMError(
                "errors.llm.unknown_provider",
                f"Unknown request_format/provider_type: {self.request_format}/{provider_type}",
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
            if self.request_format == "anthropic":
                return await self._complete_anthropic(
                    messages, max_tokens, temperature, model
                )
            if self.request_format == "response":
                return await self._complete_openai_responses(
                    messages, max_tokens, temperature, model
                )
            if self.request_format == "gemini":
                return await self._complete_gemini(
                    messages, max_tokens, temperature, model
                )
            return await self._complete_openai_chat(
                messages, max_tokens, temperature, model
            )
        except LLMError:
            raise
        except Exception as e:
            logger.exception(
                "LLM call failed",
                extra={"provider": self.provider_type, "model": model},
            )
            raise LLMError("errors.llm.call_failed", str(e)) from e

    async def stream(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        model: str | None = None,
    ) -> AsyncIterator[TokenChunk]:
        """Yield token chunks. Providers without native stream fall back to complete()."""
        model = model or self.default_model
        try:
            if self.request_format == "completion" and self._openai is not None:
                async for chunk in self._stream_openai_chat(
                    messages, max_tokens, temperature, model
                ):
                    yield chunk
                return
            # Fallback: single-shot complete → one chunk
            resp = await self.complete(
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                model=model,
            )
            if resp.content:
                yield TokenChunk(token=resp.content, finish_reason=resp.stop_reason)
            else:
                yield TokenChunk(token="", finish_reason=resp.stop_reason or "stop")
        except LLMError:
            raise
        except Exception as e:
            logger.exception(
                "LLM stream failed",
                extra={"provider": self.provider_type, "model": model},
            )
            raise LLMError("errors.llm.call_failed", str(e)) from e

    async def _stream_openai_chat(
        self, messages, max_tokens, temperature, model
    ) -> AsyncIterator[TokenChunk]:
        assert self._openai is not None
        stream = await self._openai.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        finish: str | None = None
        async for event in stream:
            choice = event.choices[0] if event.choices else None
            if choice is None:
                continue
            if choice.finish_reason:
                finish = choice.finish_reason
            delta = choice.delta.content if choice.delta else None
            if delta:
                yield TokenChunk(token=delta, finish_reason=None)
        yield TokenChunk(token="", finish_reason=finish or "stop")

    async def _complete_openai_chat(self, messages, max_tokens, temperature, model):
        assert self._openai is not None
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
        assert self._openai is not None
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
        assert self._anthropic is not None
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

    async def _complete_gemini(self, messages, max_tokens, temperature, model):
        """Google Generative Language API (generateContent)."""
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []
        for m in messages:
            role = m.get("role", "user")
            text = m.get("content", "")
            if role == "system":
                system_parts.append(text)
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": text}]})
            else:
                contents.append({"role": "user", "parts": [{"text": text}]})

        base = (self.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip(
            "/"
        )
        url = f"{base}/models/{model}:generateContent"
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system_parts:
            body["systemInstruction"] = {"parts": [{"text": "\n".join(system_parts)}]}

        async with httpx.AsyncClient(verify=self.verify_ssl, timeout=60.0) as client:
            resp = await client.post(
                url,
                params={"key": self.api_key},
                json=body,
            )
            if resp.status_code >= 400:
                raise LLMError(
                    "errors.llm.call_failed",
                    f"Gemini HTTP {resp.status_code}: {resp.text[:500]}",
                )
            data = resp.json()

        text_out = ""
        for cand in data.get("candidates") or []:
            for part in (cand.get("content") or {}).get("parts") or []:
                text_out += part.get("text") or ""
        usage = data.get("usageMetadata") or {}
        return LLMResponse(
            content=text_out,
            prompt_tokens=int(usage.get("promptTokenCount") or 0),
            completion_tokens=int(usage.get("candidatesTokenCount") or 0),
            model=model,
            stop_reason="stop",
        )


def make_client_from_env(provider_type: str, default_model: str = "gpt-4o-mini") -> LLMClient:
    """Helper: build an LLMClient using env var for API key."""
    api_key_env = {
        "openai-compatible": "OPENAI_API_KEY",
        "openai-responses": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "custom": "CUSTOM_LLM_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }.get(provider_type, "OPENAI_API_KEY")
    api_key = os.environ.get(api_key_env, "")
    base_url = (
        os.environ.get("OPENAI_BASE_URL")
        if provider_type in ("openai-compatible", "custom")
        else None
    )
    return LLMClient(
        provider_type=provider_type,
        api_key=api_key,
        base_url=base_url,
        default_model=default_model,
    )
