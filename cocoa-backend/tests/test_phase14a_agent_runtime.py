"""P14a agent_runtime tests — real LLM call loop replaces the P11c no-op skeleton.

Loads the legacy ``app/agent_runtime.py`` module via ``importlib`` (P11c
package split pattern from ``test_phase11c_agent_pod_adapter.py``) so
``monkeypatch.setattr`` can resolve module-level symbols.

Covers:
1. ``test_local_mode_calls_llm`` — local mode: LLMClient.complete() is
   called and HARNESS_CHECKPOINT fires via in-process emit().
2. ``test_k8s_mode_calls_llm_via_http`` — K8s mode: LLMClient.complete()
   is called and HARNESS_CHECKPOINT fires via emit_event() with
   ``proxy_token`` populated.
3. ``test_token_estimate_in_checkpoint_payload`` — the checkpoint payload
   carries ``token_estimate`` from ``LLMResponse.prompt_tokens +
   completion_tokens``.
4. ``test_llm_error_backoff`` — LLMError triggers 5s sleep; the loop
   continues (or exits via stop_flag).

All HTTP / DB calls are monkey-patched — no real network, no DB.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.event_types import (
    HARNESS_CHECKPOINT,
    HARNESS_LOOP_STARTED,
    HARNESS_LOOP_STOPPED,
)
from app.services.llm.llm_client import LLMResponse

_spec = importlib.util.spec_from_file_location(
    "app._agent_runtime_legacy_for_tests",
    "***REMOVED***cocoa-backend/app/agent_runtime.py",
)
_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy)
sys.modules["app._agent_runtime_legacy_for_tests"] = _legacy
import app as _app_pkg  # noqa: E402

_app_pkg._agent_runtime_legacy_for_tests = _legacy

run_agent_loop = _legacy.run_agent_loop


def _mock_llm_client(content: str = "hello", prompt_tokens: int = 11, completion_tokens: int = 22):
    """Return a mock LLMClient whose complete() returns an LLMResponse."""
    client = MagicMock(name="LLMClient")
    client.complete = AsyncMock(
        return_value=LLMResponse(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model="gpt-4o-mini",
            stop_reason="stop",
        )
    )
    return client


@asynccontextmanager
async def _fake_session_ctx():
    """A no-op async session context manager with the methods run_agent_loop needs."""
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


# ── 1. Local mode calls LLMClient ────────────────────────────────────────


@pytest.mark.asyncio
async def test_local_mode_calls_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local mode: LLMClient.complete() is called; HARNESS_CHECKPOINT fires via emit()."""
    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.is_k8s_pod_mode", lambda: False)
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._resolve_workspace_path",
        AsyncMock(return_value="/tmp/fake-ws-p14a-local"),
    )
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._should_stop_via_db",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._write_checkpoint_memory",
        AsyncMock(return_value=None),
    )

    llm_client = _mock_llm_client(content="local mode response")
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._build_llm_client",
        lambda: (llm_client, {"provider": {"max_tokens": 256, "temperature": 0.5}}),
    )

    emit_calls: list[dict] = []

    async def fake_emit(event_type, *, actor_type, actor_id=None, resource_type=None,
                        resource_id=None, payload=None, request_id=None, session):
        emit_calls.append({
            "event_type": event_type,
            "actor_type": actor_type,
            "payload": payload,
        })
        return MagicMock(id="fake-event-id")

    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.emit", fake_emit)
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests.get_session_factory",
        lambda: lambda: _fake_session_ctx(),
    )

    sleep_calls: list[float] = []

    async def fake_sleep(secs):
        sleep_calls.append(secs)
        # Stop the loop after the first checkpoint by setting the stop flag
        # via _should_stop_via_db returning True on the next iteration.
        return None

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    # Stop the loop after one iteration by overriding _should_stop_via_db
    # to flip True after the first call.
    call_count = {"n": 0}

    async def maybe_stop_via_db(instance_id):
        call_count["n"] += 1
        return call_count["n"] > 1

    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._should_stop_via_db", maybe_stop_via_db,
    )

    started = time.monotonic()
    await run_agent_loop("inst-local-p14a-1")
    elapsed = time.monotonic() - started

    assert elapsed < 2.0, f"loop should exit quickly; took {elapsed:.2f}s"

    # LLM was called at least once
    assert llm_client.complete.call_count >= 1, (
        f"LLMClient.complete() was not called (calls={llm_client.complete.call_count})"
    )

    # Checkpoint fired with the LLM-derived token_estimate
    checkpoints = [c for c in emit_calls if c["event_type"] == HARNESS_CHECKPOINT]
    assert len(checkpoints) >= 1, f"expected at least one checkpoint, got {emit_calls}"
    assert "token_estimate" in checkpoints[0]["payload"]
    assert checkpoints[0]["payload"]["token_estimate"] == 33  # 11 + 22


# ── 2. K8s mode calls LLMClient and emits via HTTP ───────────────────────


@pytest.mark.asyncio
async def test_k8s_mode_calls_llm_via_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """K8s mode: LLMClient.complete() is called; HARNESS_CHECKPOINT fires via emit_event()
    with proxy_token populated."""
    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.is_k8s_pod_mode", lambda: True)
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._resolve_workspace_path",
        AsyncMock(return_value="/tmp/fake-ws-p14a-k8s"),
    )
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests.get_proxy_token", lambda: "k8s-proxy-token",
    )

    # Force the loop to exit after one iteration by setting the stop flag
    # directly via poll_control's first response.
    async def fake_poll_control(last_seen_id):
        return [{"id": 1, "payload": {"action": "kill"}}]

    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.poll_control", fake_poll_control)

    llm_client = _mock_llm_client(content="k8s mode response", prompt_tokens=15, completion_tokens=30)
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._build_llm_client",
        lambda: (llm_client, {"provider": {"max_tokens": 512, "temperature": 0.4}}),
    )
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._write_checkpoint_memory",
        AsyncMock(return_value=None),
    )

    emit_event_calls: list[dict] = []

    async def fake_emit_event(
        event_type, actor_type, actor_id, resource_type, resource_id, payload,
    ):
        emit_event_calls.append({
            "event_type": event_type,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "payload": payload,
        })
        return f"http-event-{len(emit_event_calls)}"

    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.emit_event", fake_emit_event)

    # In-process emit() MUST NOT be called in K8s mode.
    inproc_emit_calls: list[dict] = []

    async def fake_emit(event_type, *, actor_type, actor_id=None, resource_type=None,
                        resource_id=None, payload=None, request_id=None, session):
        inproc_emit_calls.append({"event_type": event_type})
        return MagicMock(id="should-not-be-called")

    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.emit", fake_emit)

    started = time.monotonic()
    await run_agent_loop("inst-k8s-p14a-1")
    elapsed = time.monotonic() - started

    assert elapsed < 2.0, f"loop should exit on polled kill; took {elapsed:.2f}s"
    assert inproc_emit_calls == [], (
        f"in-process emit() must NOT be called in K8s mode: {inproc_emit_calls}"
    )

    # LLM was called at least once (kill arrived on poll after first iter)
    assert llm_client.complete.call_count >= 1, (
        f"LLMClient.complete() was not called (calls={llm_client.complete.call_count})"
    )

    event_types = [c["event_type"] for c in emit_event_calls]
    assert HARNESS_LOOP_STARTED in event_types
    assert HARNESS_LOOP_STOPPED in event_types
    checkpoints = [c for c in emit_event_calls if c["event_type"] == HARNESS_CHECKPOINT]
    assert len(checkpoints) >= 1, f"expected at least one checkpoint via HTTP, got {emit_event_calls}"

    first = checkpoints[0]
    assert first["payload"]["proxy_token"] == "k8s-proxy-token"
    assert first["payload"]["token_estimate"] == 45  # 15 + 30


# ── 3. token_estimate in checkpoint payload ──────────────────────────────


@pytest.mark.asyncio
async def test_token_estimate_in_checkpoint_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HARNESS_CHECKPOINT payload carries ``token_estimate`` from response tokens."""
    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.is_k8s_pod_mode", lambda: False)
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._resolve_workspace_path",
        AsyncMock(return_value="/tmp/fake-ws-tokens"),
    )

    # Stop after first iteration.
    call_count = {"n": 0}

    async def maybe_stop_via_db(instance_id):
        call_count["n"] += 1
        return call_count["n"] > 1

    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._should_stop_via_db", maybe_stop_via_db,
    )
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._write_checkpoint_memory",
        AsyncMock(return_value=None),
    )

    # Custom token counts: 100 + 250 = 350.
    llm_client = _mock_llm_client(content="custom", prompt_tokens=100, completion_tokens=250)
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._build_llm_client",
        lambda: (llm_client, {"provider": {"max_tokens": 1024, "temperature": 0.7}}),
    )

    captured_payloads: list[dict] = []

    async def fake_emit(event_type, *, actor_type, actor_id=None, resource_type=None,
                        resource_id=None, payload=None, request_id=None, session):
        if event_type == HARNESS_CHECKPOINT:
            captured_payloads.append(dict(payload or {}))
        return MagicMock(id="x")

    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.emit", fake_emit)
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests.get_session_factory",
        lambda: lambda: _fake_session_ctx(),
    )
    monkeypatch.setattr("asyncio.sleep", AsyncMock(return_value=None))

    await run_agent_loop("inst-tokens-1")

    assert len(captured_payloads) >= 1
    payload = captured_payloads[0]
    assert payload["token_estimate"] == 350, (
        f"expected token_estimate=350 (100+250), got {payload.get('token_estimate')}"
    )
    assert payload["snapshot"]["iteration"] == 0
    assert payload["snapshot"]["content_preview"] == "custom"


# ── 4. LLMError triggers 5s backoff ──────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_error_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLMError triggers sleep(5); loop continues (or exits via stop_flag)."""
    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.is_k8s_pod_mode", lambda: False)
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._resolve_workspace_path",
        AsyncMock(return_value="/tmp/fake-ws-err"),
    )

    # Stop after the LLM error retries once.
    call_count = {"n": 0}

    async def maybe_stop_via_db(instance_id):
        call_count["n"] += 1
        return call_count["n"] > 2

    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._should_stop_via_db", maybe_stop_via_db,
    )
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._write_checkpoint_memory",
        AsyncMock(return_value=None),
    )

    from app.services.llm.llm_client import LLMError

    # First call raises LLMError; subsequent calls return success.
    call_state = {"n": 0}

    async def flaky_complete(*args, **kwargs):
        call_state["n"] += 1
        if call_state["n"] == 1:
            raise LLMError("errors.llm.test", "simulated LLM failure")
        return LLMResponse(
            content="recovered",
            prompt_tokens=5,
            completion_tokens=10,
            model="gpt-4o-mini",
            stop_reason="stop",
        )

    llm_client = MagicMock(name="LLMClient-err")
    llm_client.complete = flaky_complete
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._build_llm_client",
        lambda: (llm_client, {"provider": {"max_tokens": 256, "temperature": 0.7}}),
    )

    sleep_calls: list[float] = []

    async def fake_sleep(secs):
        sleep_calls.append(secs)
        return None

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    async def fake_emit(event_type, *, actor_type, actor_id=None, resource_type=None,
                        resource_id=None, payload=None, request_id=None, session):
        return MagicMock(id="x")

    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.emit", fake_emit)
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests.get_session_factory",
        lambda: lambda: _fake_session_ctx(),
    )

    await run_agent_loop("inst-err-1")

    # First call raised LLMError → sleep(5) was called at least once
    assert 5.0 in sleep_calls, (
        f"expected asyncio.sleep(5) on LLMError, got {sleep_calls}"
    )
    # The loop continued past the error and emitted at least one successful checkpoint.
    assert call_state["n"] >= 2, (
        f"expected loop to retry after LLMError; calls={call_state['n']}"
    )
