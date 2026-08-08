"""P14a real LLM integration tests — end-to-end coverage of Wave 4.

Fifteen integration tests covering the contract between:
- builtin presets → LLMProviderConfig decoding
- LLMClient with mocked openai/anthropic SDKs (all 4 provider types)
- ModelCatalog with mocked HTTP + cache + builtin fallback
- InstanceProviderConfig per-instance overrides (DB-backed)
- agent_runtime local mode + K8s mode checkpoint emission flow
- token_estimate propagating from LLM response → harness breaker trip

All external HTTP / SDK calls are mocked via ``unittest.mock``; no real
network or DB hit occurs outside the per-test cloned DB fixture. Tests
cover the integration *boundaries* — call routing, token flow, and
breaker coupling — rather than re-testing units already covered in the
Wave 1-3 ``test_phase14a_*.py`` files.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.builtin_presets import ALL_BUILTIN_PRESETS
from app.core.event_types import (
    HARNESS_BREAKER_TRIPPED,
    HARNESS_CHECKPOINT,
    HARNESS_LOOP_STARTED,
    HARNESS_LOOP_STOPPED,
)
from app.core.events import emit
from app.core.harness_supervisor import supervisor
from app.models.event import Event
from app.models.instance_provider_config import InstanceProviderConfig
from app.models.loop_state import LoopStatus
from app.schemas.llm import LLMProviderConfig, ProviderType
from app.services.llm.llm_client import LLMClient, LLMResponse

# ── Fixtures shared across P14a integration tests ─────────────────────────


@pytest_asyncio.fixture
async def wired_factory(db_url: str):  # noqa: ARG001 — mirrors P11c pattern
    """Bind the global session factory to the per-test DB."""
    import app.core.config as cfg
    import app.core.db as db_mod

    previous_url = cfg.settings.DATABASE_URL
    cfg.settings.DATABASE_URL = db_url
    db_mod._engine = None
    db_mod._session_factory = None
    try:
        yield
    finally:
        db_mod._engine = None
        db_mod._session_factory = None
        cfg.settings.DATABASE_URL = previous_url


def _patch_sdk_constructors():
    """Patch AsyncOpenAI / AsyncAnthropic so LLMClient construction is hermetic."""
    openai_mock = MagicMock(name="AsyncOpenAI")
    anthropic_mock = MagicMock(name="AsyncAnthropic")
    return (
        patch("app.services.llm.llm_client.AsyncOpenAI", openai_mock),
        patch("app.services.llm.llm_client.AsyncAnthropic", anthropic_mock),
    )


# ── Section 1: preset manifest ↔ LLMProviderConfig (4 tests) ──────────────


def _find_preset(slug: str) -> dict:
    """Locate the builtin preset dict by its slug (public + internal)."""
    for preset in ALL_BUILTIN_PRESETS:
        if preset["slug"] == slug:
            return preset
    raise AssertionError(f"preset {slug!r} not in ALL_BUILTIN_PRESETS")


def test_fox_manifest_is_openai_compatible_with_gpt4o_mini() -> None:
    """fox manifest → openai-compatible provider + gpt-4o-mini model."""
    preset = _find_preset("fox")
    cfg = LLMProviderConfig.from_manifest_legacy(preset["manifest"])
    assert cfg.provider_type == ProviderType.openai_compatible
    assert cfg.default_model == "gpt-4o-mini"
    assert cfg.max_tokens == 2048
    assert cfg.temperature == 0.7


def test_lion_manifest_is_anthropic_with_claude_sonnet() -> None:
    """lion manifest → anthropic provider + claude-3-5-sonnet-latest."""
    preset = _find_preset("lion")
    cfg = LLMProviderConfig.from_manifest_legacy(preset["manifest"])
    assert cfg.provider_type == ProviderType.anthropic
    assert cfg.default_model == "claude-3-5-sonnet-latest"
    assert cfg.api_key_ref == "OPENAI_API_KEY"  # legacy default in decoder
    assert cfg.max_tokens == 2048


def test_beaver_manifest_is_anthropic_with_larger_budget() -> None:
    """beaver manifest → anthropic provider with 4096-token budget."""
    preset = _find_preset("beaver")
    cfg = LLMProviderConfig.from_manifest_legacy(preset["manifest"])
    assert cfg.provider_type == ProviderType.anthropic
    assert cfg.default_model == "claude-3-5-sonnet-latest"
    assert cfg.temperature == 0.5
    assert cfg.max_tokens == 4096


def test_zong_jian_manifest_has_no_provider_human_role() -> None:
    """zong-jian (Director) is human-driven — provider=None, no LLM dispatch."""
    preset = _find_preset("zong-jian")
    assert preset["manifest"]["provider"] is None, (
        "zong-jian (Director) must keep provider=None (no LLM)"
    )
    cfg = LLMProviderConfig.from_manifest_legacy(preset["manifest"])
    assert isinstance(cfg, LLMProviderConfig)
    assert preset["manifest"].get("model")


# ── Section 2: LLMClient.complete() for all 4 providers (4 tests) ─────────


@pytest.mark.asyncio
async def test_llm_client_openai_compatible_dispatches_chat_completions() -> None:
    """openai-compatible → AsyncOpenAI.chat.completions.create returns LLMResponse."""
    mock_resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=4),
        model="gpt-4o-mini",
    )
    openai_patch, _ = _patch_sdk_constructors()
    with openai_patch as openai_cls:
        client_obj = MagicMock()
        client_obj.chat.completions.create = AsyncMock(return_value=mock_resp)
        openai_cls.return_value = client_obj
        llm = LLMClient(provider_type="openai-compatible", api_key="sk-x")
        resp = await llm.complete(messages=[{"role": "user", "content": "hi"}])
    assert isinstance(resp, LLMResponse)
    assert resp.content == "ok"
    assert resp.prompt_tokens == 3 and resp.completion_tokens == 4


@pytest.mark.asyncio
async def test_llm_client_openai_responses_uses_output_text() -> None:
    """openai-responses → AsyncOpenAI.responses.create uses input_tokens/output_tokens."""
    mock_resp = SimpleNamespace(
        output_text="from-responses",
        usage=SimpleNamespace(input_tokens=8, output_tokens=9),
        model="gpt-4.1-mini",
    )
    openai_patch, _ = _patch_sdk_constructors()
    with openai_patch as openai_cls:
        client_obj = MagicMock()
        client_obj.responses.create = AsyncMock(return_value=mock_resp)
        openai_cls.return_value = client_obj
        llm = LLMClient(provider_type="openai-responses", api_key="sk-x")
        resp = await llm.complete(messages=[{"role": "user", "content": "yo"}])
    assert resp.content == "from-responses"
    assert resp.prompt_tokens == 8 and resp.completion_tokens == 9


@pytest.mark.asyncio
async def test_llm_client_anthropic_concatenates_text_blocks() -> None:
    """anthropic → AsyncAnthropic.messages.create; multiple text blocks are concatenated."""
    mock_resp = SimpleNamespace(
        content=[
            SimpleNamespace(text="part1 "),
            SimpleNamespace(text="part2"),
        ],
        usage=SimpleNamespace(input_tokens=11, output_tokens=22),
        model="claude-3-5-sonnet-20241022",
        stop_reason="end_turn",
    )
    _, anthropic_patch = _patch_sdk_constructors()
    with anthropic_patch as anthropic_cls:
        client_obj = MagicMock()
        client_obj.messages.create = AsyncMock(return_value=mock_resp)
        anthropic_cls.return_value = client_obj
        llm = LLMClient(provider_type="anthropic", api_key="sk-ant-x")
        resp = await llm.complete(
            messages=[
                {"role": "system", "content": "be brief"},
                {"role": "user", "content": "hi"},
            ],
        )
    assert resp.content == "part1 part2"
    assert resp.stop_reason == "end_turn"
    assert resp.completion_tokens == 22


@pytest.mark.asyncio
async def test_llm_client_custom_provider_uses_base_url() -> None:
    """custom provider → AsyncOpenAI is constructed with the configured base_url."""
    custom_url = "https://internal-llm-gateway.corp/api/v1"
    openai_patch, _ = _patch_sdk_constructors()
    with openai_patch as openai_cls:
        client_obj = MagicMock()
        client_obj.chat.completions.create = AsyncMock(
            return_value=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="internal"), finish_reason="stop")],
                usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3),
                model="internal-llm",
            )
        )
        openai_cls.return_value = client_obj
        llm = LLMClient(
            provider_type="custom",
            api_key="internal-key",
            base_url=custom_url,
            default_model="internal-llm",
        )
        resp = await llm.complete(messages=[{"role": "user", "content": "ping"}])
    # AsyncOpenAI was instantiated with the custom base_url (plus the
    # verify-controlled httpx client P14a injects for TLS).
    openai_cls.assert_called_once_with(
        api_key="internal-key", base_url=custom_url, http_client=ANY
    )
    assert resp.content == "internal"
    assert resp.model == "internal-llm"


# ── Section 3: ModelCatalog boundary (3 tests) ────────────────────────────


@pytest.mark.asyncio
async def test_model_catalog_provider_filter_returns_only_matches() -> None:
    """list_models(provider='openai') returns ONLY openai-prefixed entries."""
    from app.services.llm.model_catalog import _BUILTIN_FALLBACK, ModelCatalog

    payload = {
        "openai": {
            "models": {
                "gpt-4o-mini": {
                    "name": "GPT-4o Mini",
                    "limit": {"context": 128000},
                }
            }
        },
        "anthropic": {
            "models": {
                "claude-3-5-sonnet-latest": {
                    "name": "Claude 3.5 Sonnet",
                    "limit": {"context": 200000},
                }
            }
        },
    }
    mock_client = MagicMock(name="AsyncClient")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_resp = MagicMock(name="Response")
    mock_resp.raise_for_status = MagicMock(return_value=None)
    mock_resp.json = MagicMock(return_value=payload)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.services.llm.model_catalog.httpx.AsyncClient", return_value=mock_client):
        catalog = ModelCatalog()
        openai_only = await catalog.list_models(provider="openai")
        anthropic_only = await catalog.list_models(provider="anthropic")

    assert {m.id for m in openai_only} == {"gpt-4o-mini"}
    assert {m.id for m in anthropic_only} == {"claude-3-5-sonnet-latest"}
    # Unfiltered list yields at least both
    all_models = await catalog.list_models()
    assert {m.id for m in all_models} >= {"gpt-4o-mini", "claude-3-5-sonnet-latest"}
    # Built-in fallback always contains the OpenAI/Anthropic stock
    assert any(m["id"] == "gpt-4o-mini" for m in _BUILTIN_FALLBACK)


@pytest.mark.asyncio
async def test_model_catalog_search_hits_cached_results() -> None:
    """search('claude') after fetch returns cache hits — no second HTTP."""
    from app.services.llm.model_catalog import ModelCatalog

    payload = {
        "anthropic": {
            "models": {
                "claude-3-5-sonnet-latest": {"name": "Claude 3.5 Sonnet", "limit": {"context": 200000}},
                "claude-3-5-haiku-latest": {"name": "Claude 3.5 Haiku", "limit": {"context": 200000}},
            }
        },
    }
    mock_client = MagicMock(name="AsyncClient")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_resp = MagicMock(name="Response")
    mock_resp.raise_for_status = MagicMock(return_value=None)
    mock_resp.json = MagicMock(return_value=payload)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.services.llm.model_catalog.httpx.AsyncClient", return_value=mock_client):
        catalog = ModelCatalog()
        await catalog.list_models()  # triggers fetch + cache populate
        # search() is sync but reads from the populated cache.
        results = catalog.search("claude")

    assert len(results) >= 2
    assert all("claude" in m.id.lower() for m in results)


@pytest.mark.asyncio
async def test_model_catalog_fallback_includes_anthropic_models() -> None:
    """Builtin fallback ships at least 3 anthropic models even without network."""
    from app.services.llm.model_catalog import ModelCatalog

    # Make the HTTP client raise so the fallback path is taken.
    failing = MagicMock(name="AsyncClient")
    failing.__aenter__ = AsyncMock(return_value=failing)
    failing.__aexit__ = AsyncMock(return_value=None)
    import httpx
    failing.get = AsyncMock(side_effect=httpx.ConnectError("offline"))

    # Skip the committed models.dev snapshot so the chain reaches the builtin
    # fallback list (the snapshot ships newer model ids than the stock trio).
    with patch(
        "app.services.llm.model_catalog.httpx.AsyncClient", return_value=failing
    ), patch.object(ModelCatalog, "_load_bundled_raw", return_value=None):
        catalog = ModelCatalog()
        models = await catalog.list_models(provider="anthropic")

    anthropic_ids = {m.id for m in models}
    # All three stock anthropic models must survive the fallback
    assert "claude-3-5-sonnet-latest" in anthropic_ids
    assert "claude-3-5-haiku-latest" in anthropic_ids
    assert "claude-3-opus-latest" in anthropic_ids


# ── Section 4: InstanceProviderConfig per-instance override (1 test) ───────


@pytest.mark.asyncio
async def test_instance_provider_config_overrides_preset_default_model(
    session: AsyncSession, instance_factory,
) -> None:
    """A row in instance_provider_configs shadows the preset's default_model.

    Verifies the per-instance override contract: even though the preset
    manifest says ``gpt-4o-mini``, an explicit
    InstanceProviderConfig.default_model must win when the agent runtime
    resolves the active model for an instance.
    """
    from app.schemas.llm import LLMProviderConfig as _Cfg

    instance = await instance_factory()
    instance_id = instance.id

    preset = _find_preset("fox")
    preset_cfg = _LLMProviderConfig_from_preset(preset)
    assert preset_cfg.default_model == "gpt-4o-mini", (
        "baseline: preset says gpt-4o-mini"
    )

    # Per-instance override: model and provider type swap.
    override = InstanceProviderConfig(
        instance_id=instance_id,
        provider_type="anthropic",
        api_key_ref="ANTHROPIC_API_KEY",
        default_model="claude-3-5-haiku-latest",
        base_url=None,
    )
    session.add(override)
    await session.commit()

    # Reload from DB and confirm the override is what the runtime would see.
    result = await session.execute(
        select(InstanceProviderConfig).where(
            InstanceProviderConfig.instance_id == instance_id,
            InstanceProviderConfig.deleted_at.is_(None),
        )
    )
    row = result.scalars().first()
    assert row is not None
    assert row.provider_type == "anthropic"
    assert row.default_model == "claude-3-5-haiku-latest"

    # Build an LLMClient config from the override and verify the runtime path:
    # a fresh LLMProviderConfig of the row's data matches the override exactly.
    override_cfg = _Cfg(
        provider_type=ProviderType(row.provider_type),
        api_key_ref=row.api_key_ref,
        default_model=row.default_model,
    )
    assert override_cfg.provider_type == ProviderType.anthropic
    assert override_cfg.default_model != preset_cfg.default_model, (
        "override model must differ from preset default model"
    )


def _LLMProviderConfig_from_preset(preset: dict) -> LLMProviderConfig:
    return LLMProviderConfig.from_manifest_legacy(preset["manifest"])


# ── Section 5: agent_runtime with mocked LLMClient (2 tests) ───────────────


def _load_agent_runtime_module():
    """Return the canonical ``app.agent_runtime.loop`` module.

    The v4.9 convergence moved the legacy ``app/agent_runtime.py`` file
    into the package (``app/agent_runtime/loop.py``) and dropped the
    P11c importlib bridge, so the module is importable directly.
    """
    from app.agent_runtime import loop

    return loop


@asynccontextmanager
async def _fake_session_ctx():
    """No-op async session context manager."""
    session = MagicMock(name="session")
    session.commit = AsyncMock(return_value=None)
    session.flush = AsyncMock(return_value=None)
    scalars = MagicMock(name="scalars")
    scalars.first = MagicMock(return_value=None)
    scalars.all = MagicMock(return_value=[])
    result = MagicMock(name="result")
    result.scalars = MagicMock(return_value=scalars)
    session.execute = AsyncMock(return_value=result)
    session.get = AsyncMock(return_value=None)
    yield session


def _make_fake_llm_client(
    content: str = "ok", prompt_tokens: int = 10, completion_tokens: int = 20,
) -> MagicMock:
    fake = MagicMock(name="LLMClient")
    fake.complete = AsyncMock(
        return_value=LLMResponse(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model="gpt-4o-mini",
            stop_reason="stop",
        )
    )
    return fake


@pytest.mark.asyncio
async def test_agent_runtime_local_mode_emits_token_counts_to_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local mode: LLMClient.complete() returns 12+34=46 tokens → checkpoint carries them."""
    mod = _load_agent_runtime_module()

    monkeypatch.setattr(mod, "is_k8s_pod_mode", lambda: False)
    monkeypatch.setattr(
        mod, "_resolve_workspace_path",
        AsyncMock(return_value="/tmp/ws-int-local"),
    )
    # Stop after first LLM call.
    n = {"i": 0}

    async def stop_after_one(_iid: str) -> bool:
        n["i"] += 1
        return n["i"] > 1

    monkeypatch.setattr(mod, "_should_stop_via_db", stop_after_one)
    monkeypatch.setattr(mod, "_write_checkpoint_memory", AsyncMock(return_value=None))

    fake = _make_fake_llm_client(content="hi", prompt_tokens=12, completion_tokens=34)
    monkeypatch.setattr(
        mod, "_build_llm_client",
        lambda: (fake, {"provider": {"max_tokens": 1024, "temperature": 0.7}}),
    )

    captured: list[dict] = []

    async def fake_emit(
        event_type, *, actor_type, actor_id=None, resource_type=None,
        resource_id=None, payload=None, request_id=None, session,
    ):
        if event_type == HARNESS_CHECKPOINT:
            captured.append(dict(payload or {}))
        return MagicMock(id="evt")

    monkeypatch.setattr(mod, "emit", fake_emit)
    monkeypatch.setattr(mod, "get_session_factory", lambda: lambda: _fake_session_ctx())
    monkeypatch.setattr("asyncio.sleep", AsyncMock(return_value=None))

    await mod.run_agent_loop("inst-int-local-1")
    assert fake.complete.call_count >= 1
    assert captured, "no HARNESS_CHECKPOINT was emitted"
    assert captured[0]["token_estimate"] == 46


@pytest.mark.asyncio
async def test_agent_runtime_k8s_mode_emits_real_token_counts_via_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """K8s mode: real token counts flow through emit_event() to the checkpoint payload."""
    mod = _load_agent_runtime_module()

    monkeypatch.setattr(mod, "is_k8s_pod_mode", lambda: True)
    monkeypatch.setattr(
        mod, "_resolve_workspace_path",
        AsyncMock(return_value="/tmp/ws-int-k8s"),
    )
    monkeypatch.setattr(mod, "get_proxy_token", lambda: "int-proxy-tok")

    async def fake_poll_control_full(_last_seen_id: int):
        return {"events": [{"id": 1, "payload": {"action": "kill"}}], "injects": []}

    monkeypatch.setattr(mod, "poll_control_full", fake_poll_control_full)
    monkeypatch.setattr(mod, "_write_checkpoint_memory", AsyncMock(return_value=None))

    fake = _make_fake_llm_client(
        content="k8s-resp", prompt_tokens=20, completion_tokens=80,
    )
    monkeypatch.setattr(
        mod, "_build_llm_client",
        lambda: (fake, {"provider": {"max_tokens": 256, "temperature": 0.4}}),
    )

    emitted: list[dict] = []

    async def fake_emit_event(event_type, **_kwargs):
        emitted.append({"type": event_type, **_kwargs})
        return f"http-{len(emitted)}"

    monkeypatch.setattr(mod, "emit_event", fake_emit_event)

    await mod.run_agent_loop("inst-int-k8s-1")

    assert fake.complete.call_count >= 1
    checkpoints = [e for e in emitted if e["type"] == HARNESS_CHECKPOINT]
    assert checkpoints, "no checkpoint emitted via emit_event"
    cp = checkpoints[0]
    assert cp["payload"]["token_estimate"] == 100  # 20 + 80
    assert cp["payload"]["proxy_token"] == "int-proxy-tok"
    assert HARNESS_LOOP_STARTED in [e["type"] for e in emitted]
    assert HARNESS_LOOP_STOPPED in [e["type"] for e in emitted]


# ── Section 6: token_estimate → circuit breaker (1 test) ──────────────────


@pytest.mark.asyncio
async def test_token_estimate_trips_circuit_breaker_after_threshold(
    wired_factory,  # noqa: ARG001
    session: AsyncSession,
    instance_factory,
    loop_state_factory,
) -> None:
    """High-token checkpoints accumulate, then the breaker trips on max_token_estimate.

    Sets ``max_token_estimate=100`` on the loop state, then emits two
    checkpoints of 60 tokens each. After the second, the registry's
    accumulated ``token_estimate >= 100`` triggers
    ``HARNESS_BREAKER_TRIPPED`` with ``reason == "token_budget"``.
    """
    await supervisor.start()
    instance = await instance_factory()
    await loop_state_factory(
        instance,
        loop_status=LoopStatus.running.value,
        max_token_estimate=100,
        max_continuations=10_000,
        max_wall_clock_seconds=10_000,
        idle_timeout_seconds=10_000,
    )
    await session.commit()
    instance_id = instance.id  # capture eagerly — async attrs may expire post-trip

    # First checkpoint: 60 tokens, cumulative=60 (≤ 100, no trip).
    await emit(
        HARNESS_CHECKPOINT,
        actor_type="instance", actor_id=instance_id,
        resource_type="instance", resource_id=instance_id,
        payload={"token_estimate": 60, "iteration": 0},
        session=session,
    )
    await session.commit()

    metrics = supervisor.get_loop_status(instance_id)
    assert metrics["token_estimate"] == 60

    # Second checkpoint: +60 tokens pushes us to 120 ≥ 100 → breaker trips.
    await emit(
        HARNESS_CHECKPOINT,
        actor_type="instance", actor_id=instance_id,
        resource_type="instance", resource_id=instance_id,
        payload={"token_estimate": 60, "iteration": 1},
        session=session,
    )
    await session.commit()

    result = await session.execute(
        select(Event).where(
            Event.type == HARNESS_BREAKER_TRIPPED, Event.resource_id == instance_id,
        )
    )
    trip_events = list(result.scalars().all())
    assert trip_events, "expected HARNESS_BREAKER_TRIPPED after threshold"
    reasons = [e.payload.get("reason") for e in trip_events]
    assert "token_budget" in reasons, f"expected token_budget trip; got {reasons}"

    # After trip, the supervisor registry entry must be removed.
    assert instance_id not in supervisor._registry
