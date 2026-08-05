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

The canonical module is ``app.agent_runtime.loop`` (the v4.9 convergence
moved the legacy ``app/agent_runtime.py`` file into the package and
dropped the importlib shim). P14a's ``run_agent_loop`` calls
``poll_control_full`` (not the pre-v4.7 ``poll_control``), so the K8s
tests patch the full-poll function.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent_runtime import loop as _runtime
from app.core.event_types import (
    HARNESS_CHECKPOINT,
    HARNESS_LOOP_STARTED,
    HARNESS_LOOP_STOPPED,
)

run_agent_loop = _runtime.run_agent_loop

# ── 1. Local mode keeps the P8 in-process emit contract ────────────────


@pytest.mark.asyncio
async def test_local_mode_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """``is_k8s_pod_mode() == False`` → in-process emit() path runs.

    The K8s HTTP adapter (``emit_event``) MUST NOT be called; the
    in-process ``emit`` MUST be called for ``HARNESS_LOOP_STARTED``,
    at least one ``HARNESS_CHECKPOINT``, and ``HARNESS_LOOP_STOPPED``.
    """
    monkeypatch.setattr(_runtime, "is_k8s_pod_mode", lambda: False)
    monkeypatch.setattr(
        _runtime,
        "_resolve_workspace_path",
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

    monkeypatch.setattr(_runtime, "emit", fake_emit)

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
        _runtime,
        "get_session_factory",
        lambda: lambda: fake_session_ctx(),
    )

    k8s_http_calls: list[dict] = []

    async def fake_emit_event(*args, **kwargs):
        k8s_http_calls.append({"args": args, "kwargs": kwargs})
        return "fake-event-id"

    monkeypatch.setattr(_runtime, "emit_event", fake_emit_event)

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
    monkeypatch.setattr(_runtime, "is_k8s_pod_mode", lambda: True)
    monkeypatch.setattr(
        _runtime,
        "_resolve_workspace_path",
        AsyncMock(return_value="/tmp/fake-ws-k8s"),
    )
    monkeypatch.setattr(_runtime, "get_proxy_token", lambda: "test-proxy-token")

    emit_event_calls: list[dict] = []

    async def fake_emit_event(event_type, **kwargs):
        emit_event_calls.append({
            "event_type": event_type,
            **kwargs,
        })
        return f"http-event-id-{len(emit_event_calls)}"

    monkeypatch.setattr(_runtime, "emit_event", fake_emit_event)

    async def fake_poll_control_full(last_seen_id):
        return {"events": [], "injects": []}

    monkeypatch.setattr(_runtime, "poll_control_full", fake_poll_control_full)
    monkeypatch.setattr(_runtime, "_ITERATIONS", 2)
    monkeypatch.setattr(_runtime, "_ITERATION_SLEEP", 0)
    monkeypatch.setattr(_runtime, "_K8S_ITERATION_SLEEP", 0)
    monkeypatch.setattr(_runtime, "_POLL_INTERVAL", 0)

    inproc_emit_calls: list[dict] = []

    async def fake_emit(event_type, *, actor_type, actor_id=None, resource_type=None,
                        resource_id=None, payload=None, request_id=None, session):
        inproc_emit_calls.append({"event_type": event_type})
        return MagicMock(id="should-not-be-called")

    monkeypatch.setattr(_runtime, "emit", fake_emit)

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
    assert first["payload"]["snapshot"]["iteration"] == 0


# ── 3. K8s mode polls control and stops on kill ─────────────────────────


@pytest.mark.asyncio
async def test_k8s_mode_polls_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``is_k8s_pod_mode() == True`` → polling task calls ``poll_control()``
    and sets the stop flag on ``action == "kill"`` within 2 seconds.
    """
    monkeypatch.setattr(_runtime, "is_k8s_pod_mode", lambda: True)
    monkeypatch.setattr(
        _runtime,
        "_resolve_workspace_path",
        AsyncMock(return_value="/tmp/fake-ws-k8s-poll"),
    )

    emit_event_calls: list[dict] = []

    async def fake_emit_event(event_type, **kwargs):
        emit_event_calls.append({"event_type": event_type})
        return "http-event-id"

    monkeypatch.setattr(_runtime, "emit_event", fake_emit_event)

    poll_count = 0

    async def fake_poll_control_full(last_seen_id):
        nonlocal poll_count
        poll_count += 1
        if poll_count == 1:
            return {"events": [{"id": 1, "payload": {"action": "kill"}}], "injects": []}
        return {"events": [], "injects": []}

    monkeypatch.setattr(_runtime, "poll_control_full", fake_poll_control_full)
    monkeypatch.setattr(_runtime, "_ITERATIONS", 100)
    monkeypatch.setattr(_runtime, "_ITERATION_SLEEP", 0)
    monkeypatch.setattr(_runtime, "_K8S_ITERATION_SLEEP", 0)
    monkeypatch.setattr(_runtime, "_POLL_INTERVAL", 0)

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
