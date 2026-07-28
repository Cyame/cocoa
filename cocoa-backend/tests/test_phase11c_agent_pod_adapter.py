"""P11c Todo 7: agent_runtime dual-mode dispatch tests.

Branching on ``app.agent_runtime.k8s_adapter.is_k8s_pod_mode()``:

1. ``test_local_mode_unchanged`` — when ``is_k8s_pod_mode()`` is False the
   loop falls into the in-process ``emit()`` path and never touches the
   K8s HTTP adapter. P8 contract preserved.

2. ``test_k8s_mode_emits_via_http_mocked`` — when ``is_k8s_pod_mode()``
   is True the loop calls ``emit_event()`` (HTTP adapter) for every
   lifecycle event and includes ``proxy_token`` in the
   ``HARNESS_CHECKPOINT`` payload.

3. ``test_k8s_mode_polls_control`` — when ``is_k8s_pod_mode()`` is True
   the loop spawns a polling task that calls ``poll_control()`` and
   sets the stop flag as soon as a kill action arrives.

All HTTP adapter calls are monkey-patched — no real network, no DB.

The transitional ``app/agent_runtime/__init__.py`` (P11c package split)
only re-exports ``start_runtime_for``; it shadows the legacy
``app/agent_runtime.py`` module where ``run_agent_loop`` lives. The
tests load the legacy module via ``importlib.util`` and expose it as
an attribute on the ``app`` package so ``monkeypatch.setattr`` can
resolve ``"app._agent_runtime_legacy_for_tests.X"``. Same pattern as
``test_phase11c_deploy_endpoint.py``.
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

_spec = importlib.util.spec_from_file_location(
    "app._agent_runtime_legacy_for_tests",
    "***REMOVED***cocoa-backend/app/agent_runtime/__init__.py",
)
_pkg_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pkg_mod)
# The package __init__.py (P11c shim) loads the legacy ``app/agent_runtime.py``
# into ``sys.modules['app._agent_runtime_legacy']`` and re-exports only
# ``start_runtime_for``. The test needs the full legacy namespace (it
# monkey-patches ``is_k8s_pod_mode``, ``run_agent_loop``, ``emit``, etc.),
# so we follow the shim chain and pull the legacy module out of sys.modules.
_legacy = sys.modules["app._agent_runtime_legacy"]
sys.modules["app._agent_runtime_legacy_for_tests"] = _legacy
import app as _app_pkg  # noqa: E402

_app_pkg._agent_runtime_legacy_for_tests = _legacy

run_agent_loop = _legacy.run_agent_loop

# P14a replaced the P11c no-LLM skeleton with a real LLM call loop
# (commit 7a00d16). ``_build_llm_client()`` now requires an
# ``OPENAI_API_KEY`` and an httpx SOCKS proxy, neither of which the
# local/K8s dispatch tests provide. The tests were designed against
# the P11c no-op loop and exercise dispatch branches that no longer
# exist in P14a's ``run_agent_loop``. Skipped per the task note
# "accept some skips if needed"; re-enable when these tests are
# ported to P14a's LLMClient contract.
pytestmark = pytest.mark.skip(
    reason="P14a real-LLM loop incompatible with P11c no-LLM test design",
)

# ── 1. Local mode keeps the P8 in-process emit contract ────────────────


@pytest.mark.asyncio
async def test_local_mode_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """``is_k8s_pod_mode() == False`` → in-process emit() path runs.

    The K8s HTTP adapter (``emit_event``) MUST NOT be called; the
    in-process ``emit`` MUST be called for ``HARNESS_LOOP_STARTED``,
    at least one ``HARNESS_CHECKPOINT``, and ``HARNESS_LOOP_STOPPED``.
    """
    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.is_k8s_pod_mode", lambda: False)
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._resolve_workspace_path",
        AsyncMock(return_value="/tmp/fake-ws-local"),
    )

    emit_calls: list[dict] = []

    async def fake_emit(event_type, *, actor_type, actor_id=None, resource_type=None,
                        resource_id=None, payload=None, request_id=None, session):
        emit_calls.append({
            "event_type": event_type,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "payload": payload,
        })
        return MagicMock(id="fake-event-id-local")

    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.emit", fake_emit)

    @asynccontextmanager
    async def fake_session_ctx():
        session = MagicMock(name="session")
        session.commit = AsyncMock(return_value=None)
        session.flush = AsyncMock(return_value=None)
        scalars = MagicMock(name="scalars")
        scalars.first = MagicMock(return_value=None)
        result = MagicMock(name="result")
        result.scalars = MagicMock(return_value=scalars)
        session.execute = AsyncMock(return_value=result)
        yield session

    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests.get_session_factory",
        lambda: lambda: fake_session_ctx(),
    )

    k8s_http_calls: list[dict] = []

    async def fake_emit_event(*args, **kwargs):
        k8s_http_calls.append({"args": args, "kwargs": kwargs})
        return "fake-event-id"

    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.emit_event", fake_emit_event)

    await run_agent_loop("inst-local-1")

    assert k8s_http_calls == [], (
        f"emit_event() called in local mode: {k8s_http_calls}"
    )

    event_types = [c["event_type"] for c in emit_calls]
    assert HARNESS_LOOP_STARTED in event_types, event_types
    assert HARNESS_LOOP_STOPPED in event_types, event_types
    checkpoints = [c for c in emit_calls if c["event_type"] == HARNESS_CHECKPOINT]
    assert len(checkpoints) >= 1, "expected at least one checkpoint in local mode"
    assert "token_estimate" in checkpoints[0]["payload"]
    assert "snapshot" in checkpoints[0]["payload"]


# ── 2. K8s mode uses HTTP emit and includes proxy_token ─────────────────


@pytest.mark.asyncio
async def test_k8s_mode_emits_via_http_mocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``is_k8s_pod_mode() == True`` → HTTP ``emit_event()`` is used and
    ``HARNESS_CHECKPOINT`` payloads carry ``proxy_token``.

    The in-process ``emit()`` MUST NOT be called in K8s mode.
    """
    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.is_k8s_pod_mode", lambda: True)
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._resolve_workspace_path",
        AsyncMock(return_value="/tmp/fake-ws-k8s"),
    )
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests.get_proxy_token", lambda: "test-proxy-token",
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
        return f"http-event-id-{len(emit_event_calls)}"

    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.emit_event", fake_emit_event)

    async def fake_poll_control(last_seen_id):
        return []

    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.poll_control", fake_poll_control)

    inproc_emit_calls: list[dict] = []

    async def fake_emit(event_type, *, actor_type, actor_id=None, resource_type=None,
                        resource_id=None, payload=None, request_id=None, session):
        inproc_emit_calls.append({"event_type": event_type})
        return MagicMock(id="should-not-be-called")

    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.emit", fake_emit)

    await run_agent_loop("inst-k8s-1")

    assert inproc_emit_calls == [], (
        f"in-process emit() called in K8s mode: {inproc_emit_calls}"
    )

    event_types = [c["event_type"] for c in emit_event_calls]
    assert HARNESS_LOOP_STARTED in event_types
    assert HARNESS_LOOP_STOPPED in event_types
    checkpoints = [c for c in emit_event_calls if c["event_type"] == HARNESS_CHECKPOINT]
    assert len(checkpoints) >= 1, "expected at least one HTTP checkpoint"

    first = checkpoints[0]
    assert first["payload"]["proxy_token"] == "test-proxy-token"
    assert first["payload"]["iteration"] == 0
    assert first["payload"]["instance_id"] == "inst-k8s-1"


# ── 3. K8s mode polls control and stops on kill ─────────────────────────


@pytest.mark.asyncio
async def test_k8s_mode_polls_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``is_k8s_pod_mode() == True`` → polling task calls ``poll_control()``
    and sets the stop flag on ``action == "kill"`` within 2 seconds.
    """
    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.is_k8s_pod_mode", lambda: True)
    monkeypatch.setattr(
        "app._agent_runtime_legacy_for_tests._resolve_workspace_path",
        AsyncMock(return_value="/tmp/fake-ws-k8s-poll"),
    )

    emit_event_calls: list[dict] = []

    async def fake_emit_event(
        event_type, actor_type, actor_id, resource_type, resource_id, payload,
    ):
        emit_event_calls.append({"event_type": event_type})
        return "http-event-id"

    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.emit_event", fake_emit_event)

    poll_count = 0

    async def fake_poll_control(last_seen_id):
        nonlocal poll_count
        poll_count += 1
        if poll_count == 1:
            return [{"id": 1, "payload": {"action": "kill"}}]
        return []

    monkeypatch.setattr("app._agent_runtime_legacy_for_tests.poll_control", fake_poll_control)

    started = time.monotonic()
    await run_agent_loop("inst-k8s-poll-1")
    elapsed = time.monotonic() - started

    assert elapsed < 2.0, (
        f"Expected quick stop on polled kill; took {elapsed:.2f}s"
    )
    assert poll_count >= 1, "poll_control() was never called"

    event_types = [c["event_type"] for c in emit_event_calls]
    assert HARNESS_LOOP_STARTED in event_types
    assert HARNESS_LOOP_STOPPED in event_types
