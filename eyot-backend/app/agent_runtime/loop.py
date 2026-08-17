"""Agent runtime — real LLM-powered Boulder loop (P14a).

Each iteration calls ``LLMClient.complete()``, writes a ``Memory``
side-effect, and emits ``HARNESS_CHECKPOINT`` carrying real
``token_estimate`` plus the K8s ``proxy_token``. Mode is selected via
``is_k8s_pod_mode()``: local uses in-process ``emit()`` + DB status;
K8s uses HTTP ``emit_event()`` + ``poll_control()``. P14a preset
selection defaults to ``fox``. K8s-mode events (LOOP_STARTED /
CHECKPOINT / LOOP_STOPPED) all carry ``proxy_token`` (anti-spoofing).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any

from loguru import logger
from sqlalchemy import select

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

from .k8s_adapter import (
    ack_injects,
    emit_event,
    get_proxy_token,
    is_k8s_pod_mode,
    poll_control,  # noqa: F401 — module-level attribute for test monkeypatch
    poll_control_full,
)
from .safe_point import SafePointGuard

_MAX_ITERATIONS = 10_000  # safety cap; loop normally exits on stop_flag
# Test alias — phase11c monkeypatches ``_ITERATIONS`` / ``_ITERATION_SLEEP``.
_ITERATIONS = _MAX_ITERATIONS
_ITERATION_SLEEP = 0.05
_LLM_ERROR_BACKOFF_SECONDS = 5.0
_POLL_INTERVAL = 1.0
# K8s stub/idle pacing between checkpoints — avoids tight checkpoint spam
# when no real LLM is configured. Test alias: phase11c tests set it to 0
# alongside ``_ITERATIONS`` / ``_ITERATION_SLEEP``.
_K8S_ITERATION_SLEEP = 5.0


def _build_llm_client() -> tuple[Any, dict[str, Any]]:
    """Build the loop's LLMClient from the ``fox`` preset manifest.

    When no API key is configured (common in unit tests), returns a stub
    client that emits a fixed checkpoint response so the loop can still
    exercise emit / notepad / breaker paths without network credentials.
    """
    manifest: dict[str, Any] = next(
        (p.get("manifest") or {} for p in BUILTIN_PRESETS if p.get("slug") == "fox"),
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

        # Cap stub loops only for local/unit tests. K8s pods must stay alive
        # (Deployment would otherwise flap Completed ↔ Running).
        global _ITERATIONS
        if not is_k8s_pod_mode() and _ITERATIONS > 20:
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


async def _write_notepad_memory(
    instance_id: str, plan_slug: str, notepad_name: str, entry: str
) -> None:
    """v4.6 H4: mirror a notepad append as a DB ``Memory(kind=notepad)`` row.

    The DB Memory is the product truth; the ``.omo/notepads/`` file is a
    mirror. Resolves ``entity_id`` from the Instance; never writes
    ``entity_id=NULL`` — missing instance/entity skips with a log line.
    """
    from app.models.memory import Memory, MemoryKind

    async with get_session_factory()() as session:
        inst = await session.get(Instance, instance_id)
        if inst is None or inst.deleted_at is not None:
            logger.warning(
                "Notepad memory write skipped: instance missing",
                instance_id=instance_id,
            )
            return
        if not inst.entity_id:
            logger.warning(
                "Notepad memory write skipped: instance has no entity_id",
                instance_id=instance_id,
            )
            return
        memory = Memory(
            entity_id=inst.entity_id,
            kind=MemoryKind.notepad.value,
            key=f"notepad/{plan_slug}/{notepad_name}",
            content=entry[:2000],
            source_instance_id=instance_id,
        )
        session.add(memory)
        await session.flush()
        # v4.6: keep loop_state.notepad_refs as the memory-id pointer index
        # (plan storage contract: refs → memories).
        loop_state = (
            await session.execute(
                select(InstanceLoopState).where(
                    InstanceLoopState.instance_id == instance_id,
                    InstanceLoopState.deleted_at.is_(None),
                )
            )
        ).scalars().first()
        if loop_state is not None:
            refs = dict(loop_state.notepad_refs or {})
            refs[notepad_name] = memory.id
            loop_state.notepad_refs = refs
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
    # Pods talk to the backend over HTTP and do not mount DATABASE_URL.
    # Never open a DB session in K8s mode (SQLAlchemy URL would be empty).
    if k8s_mode:
        workspace_path = (
            os.environ.get("EYOT_WORKSPACE_PATH")
            or tempfile.mkdtemp(prefix=f"eyot-agent-{instance_id}-")
        )
    else:
        workspace_path = await _resolve_workspace_path(instance_id)
        if workspace_path is None:
            workspace_path = tempfile.mkdtemp(prefix=f"eyot-agent-{instance_id}-")
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
    guard = SafePointGuard()

    if k8s_mode:
        async def _apply_inject(item: dict[str, Any]) -> None:
            """Deliver one inject payload at the safe point and ack it.

            The current runtime is a stub / event-driven loop with no real
            provider tool lifecycle: applying means acking the queue row
            (the backend then emits ``harness.inject_applied``) and logging
            the payload into the loop context. Threading the payload into a
            real provider conversation is future work (v4.8+).
            """
            queue_id = item.get("queue_id")
            logger.info(
                "applying inject",
                instance_id=instance_id,
                queue_id=queue_id,
                kind=item.get("kind"),
                delivery_mode=item.get("delivery_mode"),
            )
            if queue_id:
                try:
                    acked = await ack_injects([queue_id])
                    if not acked:
                        logger.warning(
                            "inject ack reported 0 rows",
                            instance_id=instance_id, queue_id=queue_id,
                        )
                except Exception:
                    logger.opt(exception=True).warning(
                        "ack_injects failed",
                        instance_id=instance_id, queue_id=queue_id,
                    )

        async def _poll_control_loop() -> None:
            nonlocal last_seen_id
            while not stop_flag.is_set():
                try:
                    data = await poll_control_full(last_seen_id)
                except Exception:
                    logger.opt(exception=True).warning(
                        "poll_control failed; will retry", instance_id=instance_id,
                    )
                    data = {}
                for event in data.get("events", []):
                    eid = event.get("id")
                    if isinstance(eid, int):
                        last_seen_id = max(last_seen_id, eid)
                    payload = event.get("payload") or {}
                    if payload.get("action") == "kill":
                        stop_flag.set()
                        return
                for item in data.get("injects", []):
                    # Safe-point rule: soft_inject / wake are held and
                    # flushed after the current tool-result batch (never
                    # between a tool_use and its tool_result); notify
                    # deliveries ride through immediately.
                    if item.get("delivery_mode") in ("soft_inject", "wake"):
                        guard.hold(item)
                    else:
                        await _apply_inject(item)
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

            if not k8s_mode:
                try:
                    await _write_notepad_memory(
                        instance_id, "p14a-checkpoint", "learnings",
                        f"Checkpoint {i}: {response.content[:120]}",
                    )
                except Exception:
                    logger.opt(exception=True).warning(
                        "Notepad memory write failed", instance_id=instance_id, iteration=i,
                    )

            await _emit(HARNESS_CHECKPOINT, {
                "proxy_token": get_proxy_token() or "",
                "token_estimate": response.prompt_tokens + response.completion_tokens,
                "stop_reason": response.stop_reason,
                "snapshot": {"iteration": i, "content_preview": response.content[:100]},
            })
            # v4.7 H6 safe point: the current turn's tool results (none in
            # the stub loop) are complete — flush held soft-inject / wake
            # items now, BEFORE the next provider call. The guard never
            # delivers between a tool_use and its tool_result.
            if k8s_mode:
                for item in guard.flush():
                    await _apply_inject(item)
            i += 1
            # K8s stub/idle pacing — avoid tight checkpoint spam without a real LLM.
            if k8s_mode:
                await asyncio.sleep(max(_POLL_INTERVAL, _K8S_ITERATION_SLEEP))

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
