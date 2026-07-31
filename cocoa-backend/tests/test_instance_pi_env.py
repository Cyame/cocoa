"""Unit tests for OrganizationProvider → pi pod env mapping."""

from __future__ import annotations

from app.models.organization_provider import OrganizationProvider
from app.services.llm.instance_pi_env import provider_to_pi_env, redact_env_for_snapshot


def test_deepseek_maps_to_deepseek_api_key() -> None:
    provider = OrganizationProvider(
        organization_id="org",
        origin="catalog",
        catalog_provider_id="deepseek",
        name="DeepSeek",
        slug="deepseek",
        request_format="completion",
        base_url="https://api.deepseek.com",
        api_key_ref="sk-test-deepseek-key",
        default_model="deepseek-v4-flash",
    )
    env = provider_to_pi_env(provider)
    assert env["DEEPSEEK_API_KEY"] == "sk-test-deepseek-key"
    assert env["OPENAI_API_KEY"] == "sk-test-deepseek-key"
    assert env["OPENAI_BASE_URL"] == "https://api.deepseek.com"
    assert env["PI_MODEL"] == "deepseek/deepseek-v4-flash"
    assert env["PI_PROVIDER"] == "deepseek"


def test_redact_env_hides_keys() -> None:
    redacted = redact_env_for_snapshot(
        {"DEEPSEEK_API_KEY": "sk-secret", "PI_MODEL": "deepseek/x", "COCOA_API_URL": "http://x"}
    )
    assert redacted["DEEPSEEK_API_KEY"] == "***"
    assert redacted["PI_MODEL"] == "deepseek/x"
