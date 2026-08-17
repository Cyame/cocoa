"""P14a ProviderRouter tests — lazy client cache + unknown-provider error."""

from unittest.mock import MagicMock, patch

from app.services.llm.llm_client import LLMClient
from app.services.llm.provider_router import ProviderNotFoundError, ProviderRouter


def _patch_sdk_constructors():
    """Patch AsyncOpenAI / AsyncAnthropic so LLMClient construction is hermetic."""
    openai_mock = MagicMock()
    anthropic_mock = MagicMock()
    return (
        patch("app.services.llm.llm_client.AsyncOpenAI", openai_mock),
        patch("app.services.llm.llm_client.AsyncAnthropic", anthropic_mock),
    )


def test_get_client_cached() -> None:
    """Given a registered provider, get_client() returns the same instance on repeat calls."""
    openai_patch, _ = _patch_sdk_constructors()
    with openai_patch:
        router = ProviderRouter()
        router.register(
            name="foo",
            provider_type="openai-compatible",
            api_key="sk-test",
        )

        first = router.get_client("foo")
        second = router.get_client("foo")

        assert isinstance(first, LLMClient)
        assert second is first


def test_unknown_provider_raises() -> None:
    """Given no registration, get_client(unknown_name) raises ProviderNotFoundError."""
    router = ProviderRouter()

    try:
        router.get_client("nonexistent")
    except ProviderNotFoundError as exc:
        assert exc.name == "nonexistent"
    else:
        raise AssertionError("Expected ProviderNotFoundError to be raised")
