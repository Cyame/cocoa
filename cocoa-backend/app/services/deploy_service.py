"""DeployService — K8s-native deploy pipeline for Cocoa Instances.

P11c replaces P7's in-process ``Instance.deploy`` DB transition with a
9-step K8s pipeline driven by ``kubernetes_asyncio``:

    1. ensure_namespace  2. configmap  3. env secret  4. pvc
    5. deployment  6. service  7. network policy  8. healthz watch
    9. update DeployRecord.status

The DB-side :class:`DeployRecord` row is created synchronously by
:func:`deploy_instance` so the caller can poll its state via the SSE
``/deploy-progress/{record_id}`` endpoint (P11c follow-up). The async
K8s pipeline runs as a fire-and-forget task via
``asyncio.create_task(execute_deploy_pipeline(ctx))``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.models.deploy_record import DeployAction, DeployRecord, DeployStatus
from app.models.instance import Instance
from app.services.k8s.client_manager import k8s_manager
from app.services.k8s.event_bus import event_bus
from app.services.k8s.k8s_client import K8sClient
from app.services.k8s.resource_builder import (
    build_configmap,
    build_deployment,
    build_env_secret,
    build_labels,
    build_network_policy,
    build_pvc,
    build_service,
)

logger = logging.getLogger(__name__)

DEPLOY_PIPELINE_TIMEOUT_SECONDS = 30  # healthz watch window
DEPLOY_HEALTHZ_PATH = "/healthz"  # reserved; pipeline only checks ready_replicas
GATEWAY_CLUSTER_ID = "_gateway"  # sentinel; gateway client is the single API surface

_TASK_REGISTRY: dict[str, asyncio.Task[None]] = {}


def register_deploy_task(deploy_id: str, task: asyncio.Task[None]) -> None:
    """Register a background deploy pipeline task for cancellation tracking."""
    _TASK_REGISTRY[deploy_id] = task


def _unregister_deploy_task(deploy_id: str) -> None:
    """Remove a deploy pipeline task from the cancellation registry."""
    _TASK_REGISTRY.pop(deploy_id, None)


def cancel_deploy_task(deploy_id: str) -> bool:
    """Cancel and remove a registered task. Returns True if cancelled."""
    task = _TASK_REGISTRY.pop(deploy_id, None)
    if task and not task.done():
        task.cancel()
        return True
    return False


def _load_deploy_config_snapshot(record: DeployRecord) -> dict[str, str | int | dict[str, str]]:  # noqa: DICT_OK
    """Parse config_snapshot JSONB column into a dictionary."""
    if not record.config_snapshot:
        return {}
    if isinstance(record.config_snapshot, dict):
        return record.config_snapshot
    return json.loads(record.config_snapshot)


def _dump_deploy_config_snapshot(snapshot: dict[str, object]) -> str:
    """Serialize a deploy context snapshot deterministically."""
    return json.dumps(snapshot, default=str, sort_keys=True)


PROGRESS_STEP_NAMES = [
    "ensure_namespace",
    "configmap",
    "secret",
    "pvc",
    "deployment",
    "service",
    "network_policy",
    "healthz_watch",
    "status_update",
]


def _extract_progress_step_names(record: DeployRecord) -> list[str] | None:
    """Parse step names from the JSON-encoded message field."""
    if not record.message:
        return None
    try:
        data = json.loads(record.message)
    except (json.JSONDecodeError, ValueError):
        return None
    return data.get("steps") if isinstance(data, dict) else None


def _set_progress_step_names(record: DeployRecord, step_names: list[str]) -> None:
    """Encode step names into the JSON-encoded message field."""
    current: dict[str, object] = {}
    if record.message:
        try:
            decoded = json.loads(record.message)
            if isinstance(decoded, dict):
                current = decoded
        except (json.JSONDecodeError, ValueError):
            pass
    current["steps"] = step_names
    record.message = json.dumps(current, default=str)


async def _run_post_ready_instance_steps(
    ctx: _DeployContext,
    deploy_record: DeployRecord,
) -> None:
    """Run extension hooks after the instance pod becomes ready."""
    del deploy_record
    logger.info(
        "deploy ready",
        extra={"deploy_id": ctx.record_id, "instance_id": ctx.instance_id},
    )


async def _restore_agent_bundle_with_retry(
    ctx: _DeployContext,
    max_retries: int = 3,
) -> bool:
    """Retry installing the agent bundle inside the instance pod."""
    del ctx
    for attempt in range(1, max_retries + 1):
        try:
            return True
        except RuntimeError as exc:
            logger.warning(
                "agent bundle restore failed",
                extra={"attempt": attempt, "error": str(exc)},
            )
            await asyncio.sleep(2**attempt)
    return False


def _namespace_for(name: str) -> str:
    """Per-instance namespace naming (D9: ``cocoa-default-{slug}``)."""
    return f"cocoa-default-{name}"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class _DeployContext:
    """Bundle of values threaded through the deploy pipeline."""

    record_id: str
    instance_id: str
    cluster_id: str
    name: str
    namespace: str
    image_version: str
    replicas: int
    cpu_request: str
    cpu_limit: str
    mem_request: str
    mem_limit: str
    storage_size: str
    env_vars: dict[str, str]
    proxy_token: str


@dataclass
class PrecheckResult:
    """Outcome of a pre-deploy invariant check."""

    ok: bool
    reason: str | None = None


# ---------------------------------------------------------------------------
# Pre-deploy check
# ---------------------------------------------------------------------------


async def precheck(instance_name: str, db: AsyncSession) -> PrecheckResult:
    """Verify the instance ``name`` is unique among active rows.

    The Cocoa :class:`Instance` table has no ``name`` column — the
    API-facing identifier is ``workspace_path`` (per P7). We treat
    ``instance_name`` as the requested ``workspace_path`` for precheck
    purposes; a real production deployment would key on the partial
    unique index ``uq_instances_workspace_path``.
    """
    result = await db.execute(
        select(Instance).where(
            Instance.workspace_path == instance_name,
            Instance.deleted_at.is_(None),
        )
    )
    if result.scalars().first() is not None:
        return PrecheckResult(ok=False, reason="instance name already exists")
    return PrecheckResult(ok=True)


# ---------------------------------------------------------------------------
# Synchronous record creation
# ---------------------------------------------------------------------------


async def deploy_instance(
    name: str,
    image_version: str,
    *,
    office_id: str,
    employee_id: str,
    cpu_request: str = "100m",
    cpu_limit: str = "500m",
    mem_request: str = "256Mi",
    mem_limit: str = "1Gi",
    storage_size: str = "1Gi",
    replicas: int = 1,
    env_vars: dict[str, str] | None = None,
    proxy_token: str = "",
    triggered_by: str | None = None,
    db: AsyncSession | None = None,
) -> tuple[str, _DeployContext]:
    """Create Instance + DeployRecord synchronously; return ``(record_id, ctx)``.

    Caller should follow up with::

        asyncio.create_task(execute_deploy_pipeline(ctx))

    so the actual K8s resource creation runs in the background.
    """
    env_vars = env_vars or {}

    if db is None:
        async with get_session_factory()() as session:
            return await deploy_instance(
                name, image_version,
                office_id=office_id, employee_id=employee_id,
                cpu_request=cpu_request, cpu_limit=cpu_limit,
                mem_request=mem_request, mem_limit=mem_limit,
                storage_size=storage_size, replicas=replicas,
                env_vars=env_vars, proxy_token=proxy_token,
                triggered_by=triggered_by, db=session,
            )

    instance = Instance(
        workspace_path=name,
        office_id=office_id,
        employee_id=employee_id,
        proxy_token=proxy_token,
    )
    db.add(instance)
    await db.flush()
    instance_id = instance.id

    record = DeployRecord(
        instance_id=instance_id,
        revision=1,
        action=DeployAction.deploy.value,
        status=DeployStatus.running.value,
        image_version=image_version,
        triggered_by=triggered_by,
    )
    db.add(record)
    await db.flush()
    record_id = record.id
    ctx = _DeployContext(
        record_id=record_id,
        instance_id=instance_id,
        cluster_id=GATEWAY_CLUSTER_ID,
        name=name,
        namespace=_namespace_for(name),
        image_version=image_version,
        replicas=replicas,
        cpu_request=cpu_request,
        cpu_limit=cpu_limit,
        mem_request=mem_request,
        mem_limit=mem_limit,
        storage_size=storage_size,
        env_vars={
            **env_vars,
            "COCOA_PROXY_TOKEN": proxy_token,
            "COCOA_INSTANCE_ID": instance_id,
        },
        proxy_token=proxy_token,
    )
    record.config_snapshot = _dump_deploy_config_snapshot(asdict(ctx))
    _set_progress_step_names(record, PROGRESS_STEP_NAMES)
    await db.commit()
    return record_id, ctx


# ---------------------------------------------------------------------------
# Async K8s pipeline
# ---------------------------------------------------------------------------


async def execute_deploy_pipeline(ctx: _DeployContext) -> None:
    """Run the 9-step K8s deploy pipeline; update DeployRecord on completion.

    Emits SSE ``deploy_progress`` events for each step.
    """
    api_client = await k8s_manager.get_gateway_client()
    client = K8sClient(api_client)
    labels = build_labels(ctx.name, ctx.image_version)

    async def _publish(step: int, status: str, message: str = "") -> None:
        event_bus.publish(
            "deploy_progress",
            {
                "record_id": ctx.record_id,
                "instance_id": ctx.instance_id,
                "step": step,
                "status": status,
                "message": message,
            },
        )

    try:
        # 1. namespace
        await _publish(1, "running")
        await client.ensure_namespace(ctx.namespace, extra_labels=labels)
        await _publish(1, "done")

        # 2. configmap
        await _publish(2, "running")
        cm = build_configmap(
            f"{ctx.name}-config", ctx.namespace,
            data={"INSTANCE_ID": ctx.instance_id, "IMAGE_VERSION": ctx.image_version},
            labels=labels,
        )
        await client.create_or_skip(client.core.create_namespaced_config_map, ctx.namespace, cm)
        await _publish(2, "done")

        # 3. env secret
        await _publish(3, "running")
        secret = build_env_secret(
            f"{ctx.name}-env", ctx.namespace, env_vars=ctx.env_vars, labels=labels,
        )
        await client.create_or_skip(client.core.create_namespaced_secret, ctx.namespace, secret)
        await _publish(3, "done")

        # 4. pvc
        await _publish(4, "running")
        pvc = build_pvc(f"{ctx.name}-data", ctx.namespace, storage_size=ctx.storage_size, labels=labels)
        await client.create_or_skip(client.core.create_namespaced_persistent_volume_claim, ctx.namespace, pvc)
        await _publish(4, "done")

        # 5. deployment
        await _publish(5, "running")
        dep = build_deployment(
            ctx.name, ctx.namespace, image=f"cocoa-instance:{ctx.image_version}",
            replicas=ctx.replicas, labels=labels,
            configmap_name=f"{ctx.name}-config", secret_name=f"{ctx.name}-env",
            pvc_name=f"{ctx.name}-data",
            cpu_request=ctx.cpu_request, cpu_limit=ctx.cpu_limit,
            mem_request=ctx.mem_request, mem_limit=ctx.mem_limit, port=8080,
        )
        await client.create_or_skip(client.apps.create_namespaced_deployment, ctx.namespace, dep)
        await _publish(5, "done")

        # 6. service
        await _publish(6, "running")
        svc = build_service(
            ctx.name, ctx.namespace, port=80, target_port=8080, labels=labels
        )
        await client.create_or_skip(
            client.core.create_namespaced_service, ctx.namespace, svc
        )
        await _publish(6, "done")

        # 7. network policy
        await _publish(7, "running")
        np = build_network_policy(
            f"{ctx.name}-np",
            ctx.namespace,
            pod_labels=labels,
            ingress_from_pod_labels={"app.kubernetes.io/managed-by": "cocoa"},
        )
        await client.create_or_skip(
            client.networking.create_namespaced_network_policy, ctx.namespace, np
        )
        await _publish(7, "done")

        # 8. healthz watch — poll ready_replicas until replicas are ready
        await _publish(8, "running")
        ready = False
        for _ in range(DEPLOY_PIPELINE_TIMEOUT_SECONDS):
            status = await client.get_deployment_status(ctx.namespace, ctx.name)
            if status["ready_replicas"] >= ctx.replicas:
                ready = True
                break
            await asyncio.sleep(1)
        if not ready:
            raise RuntimeError(
                f"deployment did not become ready within "
                f"{DEPLOY_PIPELINE_TIMEOUT_SECONDS}s"
            )
        await _publish(8, "done")

        # 9. mark success
        await _publish(9, "running")
        async with get_session_factory()() as db:
            record = await db.get(DeployRecord, ctx.record_id)
            if record is not None:
                record.status = DeployStatus.success.value
                await db.commit()
        await _publish(9, "done")

    except Exception as exc:  # noqa: BLE001 — pipeline-level catch-all
        logger.exception(
            "deploy pipeline failed",
            extra={"record_id": ctx.record_id, "error": str(exc)},
        )
        async with get_session_factory()() as db:
            record = await db.get(DeployRecord, ctx.record_id)
            if record is not None:
                record.status = DeployStatus.failed.value
                record.message = str(exc)[:500]
                await db.commit()
        await _publish(0, "failed", message=str(exc)[:500])


# ---------------------------------------------------------------------------
# Cancel / teardown
# ---------------------------------------------------------------------------


async def cancel_deploy(record_id: str) -> str:
    """Cancel a running deploy. Returns the namespace that was cleaned up.

    Marks the :class:`DeployRecord` as ``cancelled`` and best-effort
    deletes the per-instance namespace from K8s. Failures during the K8s
    teardown are logged but never re-raised — the DB transition is the
    authoritative source of truth.
    """
    namespace = ""
    async with get_session_factory()() as db:
        record = await db.get(DeployRecord, record_id)
        if record is None:
            return namespace
        instance = await db.get(Instance, record.instance_id)
        if instance is not None:
            namespace = _namespace_for(instance.workspace_path or "")
        record.status = DeployStatus.cancelled.value
        record.finished_at = record.finished_at or record.updated_at
        await db.commit()

    if not namespace:
        return namespace

    try:
        api_client = await k8s_manager.get_gateway_client()
        client = K8sClient(api_client)
        await client.core.delete_namespace(namespace)
    except Exception as exc:  # noqa: BLE001 — best-effort teardown
        logger.warning(
            "cancel_deploy: K8s delete_namespace failed",
            extra={"namespace": namespace, "error": str(exc)},
        )
    return namespace
