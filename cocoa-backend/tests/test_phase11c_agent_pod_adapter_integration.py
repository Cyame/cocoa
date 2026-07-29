"""P11c integration coverage for agent-runtime pod/local mode wiring."""

from __future__ import annotations

import importlib.util
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_types import HARNESS_CHECKPOINT, HARNESS_LOOP_STARTED, HARNESS_LOOP_STOPPED
from app.core.event_watcher import EventWatcher
from app.core.events import register_handler

_RUNTIME_MODULE = "app._agent_runtime_p11c_integration"
_RUNTIME_PATH = Path(__file__).parents[1] / "app" / "agent_runtime.py"
_spec = importlib.util.spec_from_file_location(_RUNTIME_MODULE, _RUNTIME_PATH)
assert _spec is not None and _spec.loader is not None
_runtime = importlib.util.module_from_spec(_spec)
sys.modules[_RUNTIME_MODULE] = _runtime
_spec.loader.exec_module(_runtime)
run_agent_loop = _runtime.run_agent_loop


def _configure_k8s_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    proxy_token: str = "pod-proxy-token",
) -> tuple[AsyncMock, AsyncMock]:
    """Configure a one-iteration K8s loop and return its HTTP mocks."""
    emit_event = AsyncMock(return_value="event-id")
    poll_control = AsyncMock(return_value=[])
    monkeypatch.setattr(_runtime, "is_k8s_pod_mode", lambda: True)
    monkeypatch.setattr(_runtime, "_resolve_workspace_path", AsyncMock(return_value="/tmp/p11c-pod"))
    monkeypatch.setattr(_runtime, "get_proxy_token", lambda: proxy_token)
    monkeypatch.setattr(_runtime, "emit_event", emit_event)
    monkeypatch.setattr(_runtime, "poll_control", poll_control)
    monkeypatch.setattr(_runtime, "_ITERATIONS", 1)
    monkeypatch.setattr(_runtime, "_ITERATION_SLEEP", 0)
    return emit_event, poll_control


@pytest.mark.asyncio
async def test_k8s_mode_emits_via_http_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pod-mode loop sends lifecycle and checkpoint events over HTTP."""
    emit_event, _ = _configure_k8s_runtime(monkeypatch)
    in_process_emit = AsyncMock()
    monkeypatch.setattr(_runtime, "emit", in_process_emit)
    await run_agent_loop("instance-http")

    event_types = [call.args[0] for call in emit_event.await_args_list]
    assert event_types == [HARNESS_LOOP_STARTED, HARNESS_CHECKPOINT, HARNESS_LOOP_STOPPED]
    in_process_emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_k8s_mode_polls_control_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """A polled kill event stops the pod loop within the two-second bound."""
    emit_event, poll_control = _configure_k8s_runtime(monkeypatch)
    poll_control.return_value = [{"id": 1, "payload": {"action": "kill"}}]
    monkeypatch.setattr(_runtime, "_ITERATIONS", 10)

    with anyio.fail_after(2):
        await run_agent_loop("instance-kill")

    poll_control.assert_awaited()
    event_types = [call.args[0] for call in emit_event.await_args_list]
    assert event_types.count(HARNESS_CHECKPOINT) <= 1
    assert event_types[-1] == HARNESS_LOOP_STOPPED


@pytest.mark.asyncio
async def test_local_mode_unchanged_integration(
    session: AsyncSession,
    instance_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local mode persists through in-process emit and runs the handler chain."""
    instance = await instance_factory(workspace_path="local-runtime-integration")
    handler = AsyncMock()
    register_handler(HARNESS_CHECKPOINT, handler)
    emit_spy = AsyncMock(wraps=_runtime.emit)
    monkeypatch.setattr(_runtime, "is_k8s_pod_mode", lambda: False)
    monkeypatch.setattr(_runtime, "_resolve_workspace_path", AsyncMock(return_value="/tmp/p11c-local"))
    monkeypatch.setattr(_runtime, "append_to_notepad", AsyncMock())
    monkeypatch.setattr(_runtime, "emit", emit_spy)
    monkeypatch.setattr(_runtime, "emit_event", AsyncMock())
    monkeypatch.setattr(_runtime, "_ITERATIONS", 1)
    monkeypatch.setattr(_runtime, "_ITERATION_SLEEP", 0)

    @asynccontextmanager
    async def session_context():
        yield session

    monkeypatch.setattr(_runtime, "get_session_factory", lambda: lambda: session_context())
    await run_agent_loop(instance.id)

    event_types = [call.args[0] for call in emit_spy.await_args_list]
    assert event_types == [HARNESS_LOOP_STARTED, HARNESS_CHECKPOINT, HARNESS_LOOP_STOPPED]
    handler.assert_awaited_once()
    _runtime.emit_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_proxy_token_in_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pod checkpoint payload carries the injected proxy token."""
    emit_event, _ = _configure_k8s_runtime(monkeypatch, proxy_token="proxy-from-env")
    await run_agent_loop("instance-proxy")
    checkpoint = next(
        call for call in emit_event.await_args_list if call.args[0] == HARNESS_CHECKPOINT
    )
    assert checkpoint.kwargs["payload"]["proxy_token"] == "proxy-from-env"
    assert checkpoint.kwargs["payload"].get("token_estimate") is not None
    assert checkpoint.kwargs["payload"].get("snapshot", {}).get("iteration") == 0


@pytest.mark.asyncio
async def test_event_watcher_dispatches_to_handlers_mocked() -> None:
    """The watcher dispatches a mocked newly-polled row to registered handlers."""
    event = SimpleNamespace(
        id=7,
        type="agent.pod.integration",
        actor_type="agent_pod",
        actor_id="pod-7",
        resource_type="instance",
        resource_id="instance-7",
        payload={"checkpoint": 7},
        request_id="request-7",
        created_at=datetime.now(UTC),
    )
    handler = AsyncMock()
    register_handler("agent.pod.*", handler)
    result = MagicMock()
    result.scalars.return_value.all.return_value = [event]
    session = AsyncMock()
    session.execute.return_value = result
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    session_factory = MagicMock(return_value=context)

    with patch("app.core.event_watcher.get_session_factory", return_value=session_factory):
        await EventWatcher()._poll_once()

    handler.assert_awaited_once()
    assert handler.await_args.kwargs["resource_id"] == "instance-7"
    assert handler.await_args.kwargs["payload"] == {"checkpoint": 7}
