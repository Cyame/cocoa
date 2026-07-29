"""Agent runtime — real LLM-powered Boulder loop (P14a).

Each iteration calls ``LLMClient.complete()``, writes a ``Memory``
side-effect, and emits ``HARNESS_CHECKPOINT`` carrying real
``token_estimate`` plus the K8s ``proxy_token``. Mode is selected via
``is_k8s_pod_mode()``: local uses in-process ``emit()`` + DB status;
K8s uses HTTP ``emit_event()`` + ``poll_control()``. P14a preset
selection defaults to ``mi-shi``. K8s-mode events (LOOP_STARTED /
CHECKPOINT / LOOP_STOPPED) all carry ``proxy_token`` (anti-spoofing).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any

from loguru import logger
from sqlalchemy import select

from app.agent_runtime.k8s_adapter import (
    emit_event,
    get_proxy_token,
    is_k8s_pod_mode,
    poll_control,
)
from app.core.builtin_presets import BUILTIN_PRESETS
from app.core.db import get_session_factory
from app.core.event_types import (
    HARNESS_CHECKPOINT,
    HARNESS_CONTROL_SENT,
    HARNESS_LOOP_STARTED,
    HARNESS_LOOP_STOPPED,
)
from app.core.events import emit, register_handler
from app.core.harness_supervisor import supervisor
from app.core.notepad import append_to_notepad
from app.models.instance import Instance
from app.models.loop_state import InstanceLoopState, LoopStatus
from app.schemas.llm import LLMProviderConfig
from app.services.llm.llm_client import LLMClient, LLMError

_MAX_ITERATIONS = 10_000  # safety cap; loop normally exits on stop_flag
# Test alias — phase11c monkeypatches ``_ITERATIONS`` / ``_ITERATION_SLEEP``.
_ITERATIONS = _MAX_ITERATIONS
_ITERATION_SLEEP = 0.05
_LLM_ERROR_BACKOFF_SECONDS = 5.0
_POLL_INTERVAL = 1.0


def _build_llm_client() -> tuple[Any, dict[str, Any]]:
    """Build the loop's LLMClient from the ``mi-shi`` preset manifest.

    When no API key is configured (common in unit tests), returns a stub
    client that emits a fixed checkpoint response so the loop can still
    exercise emit / notepad / breaker paths without network credentials.
    """
    manifest: dict[str, Any] = next(
        (p.get("manifest") or {} for p in BUILTIN_PRESETS if p.get("slug") == "mi-shi"),
        {},
    )
    cfg = LLMProviderConfig.from_manifest_legacy(manifest)
    api_key = os.environ.get(cfg.api_key_ref, "") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        class _StubResponse:
            content = "stub checkpoint"
            prompt_tokens = 1
            completion_tokens = 1
            stop_reason = "stop"

        class _StubClient:
            async def complete(self, **_kwargs: Any) -> _StubResponse:
                await asyncio.sleep(_ITERATION_SLEEP)
                return _StubResponse()

        # Cap stub loops so unit tests without credentials cannot hang forever.
        global _ITERATIONS
        if _ITERATIONS > 20:
            _ITERATIONS = 3
        return _StubClient(), manifest

    client = LLMClient(
        provider_type=cfg.provider_type.value,
        api_key=api_key,
        base_url=cfg.base_url,
        default_model=cfg.default_model,
    )
    return client, manifest


async def _should_stop_via_db(instance_id: str) -> bool:
    """Return True iff DB ``InstanceLoopState.loop_status`` indicates stop."""
    async with get_session_factory()() as session:
        result = await session.execute(
            select(InstanceLoopState).where(
                InstanceLoopState.instance_id == instance_id,
                InstanceLoopState.deleted_at.is_(None),
            )
        )
        loop_state = result.scalars().first()
        if loop_state is None:
            return False
        return loop_state.loop_status in (
            LoopStatus.interrupted.value,
            LoopStatus.paused.value,
            LoopStatus.completed.value,
            LoopStatus.failed.value,
        )


async def _write_checkpoint_memory(instance_id: str, summary: str) -> None:
    """Append a ``Memory`` for the LLM's latest output; no-op when instance is missing."""
    from app.models.memory import Memory, MemoryKind

    async with get_session_factory()() as session:
        inst = await session.get(Instance, instance_id)
        if inst is None or inst.deleted_at is not None:
            return
        session.add(Memory(
            entity_id=inst.entity_id,
            kind=MemoryKind.experience.value,
            key=f"checkpoint_{instance_id}",
            content=summary[:500],
            source_instance_id=instance_id,
        ))
        await session.commit()


async def _resolve_workspace_path(instance_id: str) -> str | None:
    """Read ``Instance.workspace_path`` from DB."""
    async with get_session_factory()() as session:
        result = await session.execute(
            select(Instance).where(Instance.id == instance_id)
        )
        instance = result.scalars().first()
        return instance.workspace_path if instance else None


async def run_agent_loop(instance_id: str) -> None:
    """Run the LLM-powered agent loop for one Instance."""
    k8s_mode = is_k8s_pod_mode()
    workspace_path = await _resolve_workspace_path(instance_id)
    if workspace_path is None:
        workspace_path = tempfile.mkdtemp(prefix=f"cocoa-agent-{instance_id}-")
        logger.warning(
            "Instance has no workspace_path; using tempfile fallback",
            instance_id=instance_id, fallback=workspace_path,
        )

    preset_manifest: dict[str, Any] = {}
    try:
        llm_client, preset_manifest = _build_llm_client()
    except LLMError as e:
        logger.error(
            "Failed to build LLMClient from manifest; loop will exit",
            instance_id=instance_id, error=str(e),
        )
        return

    provider_cfg = preset_manifest.get("provider", {})
    max_tokens = int(provider_cfg.get("max_tokens", 1024))
    temperature = float(provider_cfg.get("temperature", 0.7))

    stop_flag = asyncio.Event()
    last_seen_id = 0
    control_task: asyncio.Task | None = None

    if k8s_mode:
        async def _poll_control_loop() -> None:
            nonlocal last_seen_id
            while not stop_flag.is_set():
                try:
                    events = await poll_control(last_seen_id)
                except Exception:
                    logger.opt(exception=True).warning(
                        "poll_control failed; will retry", instance_id=instance_id,
                    )
                    events = []
                for event in events:
                    eid = event.get("id")
                    if isinstance(eid, int):
                        last_seen_id = max(last_seen_id, eid)
                    payload = event.get("payload") or {}
                    if payload.get("action") == "kill":
                        stop_flag.set()
                        return
                await asyncio.sleep(_POLL_INTERVAL)

        control_task = asyncio.create_task(_poll_control_loop())
    else:
        async def _on_control(**kwargs: object) -> None:
            payload = kwargs.get("payload") or {}
            if payload.get("instance_id") == instance_id and payload.get("action") == "kill":
                stop_flag.set()

        register_handler(HARNESS_CONTROL_SENT, _on_control)

    async def _emit(event_type: str, payload: dict[str, Any]) -> None:
        """Emit one event — HTTP in K8s mode, in-process in local mode.

        K8s-mode payloads carry ``proxy_token`` on every event so the
        backend can attribute and authenticate the pod (anti-spoofing).
        """
        if k8s_mode:
            await emit_event(
                event_type,
                actor_type="instance", actor_id=instance_id,
                resource_type="instance", resource_id=instance_id,
                payload=payload,
            )
        else:
            async with get_session_factory()() as s:
                await emit(
                    event_type,
                    actor_type="instance", actor_id=instance_id,
                    resource_type="instance", resource_id=instance_id,
                    payload=payload, session=s,
                )
                await s.commit()

    try:
        await _emit(HARNESS_LOOP_STARTED, {"proxy_token": get_proxy_token() or ""})

        i = 0
        while not stop_flag.is_set() and i < _ITERATIONS:
            if not k8s_mode and await _should_stop_via_db(instance_id):
                logger.info("Agent loop stopping on DB status change", instance_id=instance_id)
                break

            try:
                response = await llm_client.complete(
                    messages=[{
                        "role": "user",
                        "content": (
                            f"checkpoint #{i} for instance {instance_id}; "
                            "produce a brief status update."
                        ),
                    }],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except LLMError as e:
                logger.error(
                    "LLM call failed; backing off",
                    instance_id=instance_id, iteration=i, error=str(e),
                )
                await asyncio.sleep(_LLM_ERROR_BACKOFF_SECONDS)
                continue

            if not k8s_mode:
                try:
                    await _write_checkpoint_memory(instance_id, response.content[:200])
                except Exception:
                    logger.opt(exception=True).warning(
                        "Checkpoint memory write failed",
                        instance_id=instance_id,
                        iteration=i,
                    )

            if not k8s_mode:
                try:
                    await append_to_notepad(
                        workspace_path, "p14a-checkpoint", "learnings",
                        f"Checkpoint {i}: {response.content[:120]}",
                    )
                except Exception:
                    logger.opt(exception=True).warning(
                        "Notepad append failed", instance_id=instance_id, iteration=i,
                    )

            await _emit(HARNESS_CHECKPOINT, {
                "proxy_token": get_proxy_token() or "",
                "token_estimate": response.prompt_tokens + response.completion_tokens,
                "stop_reason": response.stop_reason,
                "snapshot": {"iteration": i, "content_preview": response.content[:100]},
            })
            i += 1

        await _emit(
            HARNESS_LOOP_STOPPED,
            {"proxy_token": get_proxy_token() or "", "iterations": i},
        )
    finally:
        supervisor._runtime_tasks.pop(instance_id, None)
        if control_task is not None:
            control_task.cancel()
            try:
                await control_task
            except asyncio.CancelledError:
                pass
        stop_flag.set()


async def start_runtime_for(instance_id: str) -> None:
    """Start the agent runtime task for *instance_id* if not already running."""
    if instance_id in supervisor._runtime_tasks:
        return
    task = asyncio.create_task(run_agent_loop(instance_id))
    supervisor._runtime_tasks[instance_id] = task
    logger.info("Agent runtime task started", instance_id=instance_id)
