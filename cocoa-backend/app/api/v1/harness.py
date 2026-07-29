"""P8 harness control command endpoints.

Hosts the 5 P8 action endpoints that drive the agent loop state machine:

- ``POST /instances/{id}/interrupt`` — kill signal + mark interrupted
- ``POST /instances/{id}/pause`` — mark paused
- ``POST /instances/{id}/resume`` — mark running + start runtime task
- ``GET /instances/{id}/status`` — merged DB + in-memory metrics
- ``POST /instances/{id}/snapshot`` — capture & validate boulder snapshot

URL prefix is ``/instances`` (same as :mod:`app.api.v1.instances`) so the
existing client paths stay stable. The router is registered separately
in :mod:`app.api.v1.router` so the endpoints live in a module under the
250 LOC ceiling.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.agent_runtime import start_runtime_for
from app.api.deps import DB, CurrentUserDep
from app.core.errors import NotFoundError
from app.core.harness_supervisor import supervisor
from app.core.openapi import add_error_responses
from app.core.permissions import require_workspace_role
from app.models.instance import Instance
from app.models.loop_state import InstanceLoopState
from app.schemas.loop_state import BoulderSnapshotOut, InstanceLoopStateOut

router = APIRouter(prefix="/instances", tags=["Instances"])
add_error_responses(router)


async def _get_instance_or_404(instance_id: str, db) -> Instance:
    """Fetch an active instance or raise the standard not-found error."""
    instance = await db.get(Instance, instance_id)
    if instance is None or instance.deleted_at is not None:
        raise NotFoundError(
            "instance.not_found",
            "errors.instance.not_found",
            f"Instance '{instance_id}' not found",
        )
    return instance


def _to_status_payload(state: InstanceLoopState) -> dict:
    """Merge DB loop state with in-memory supervisor metrics."""
    metrics = supervisor.get_loop_status(state.instance_id)
    return {
        "instance_id": state.instance_id,
        "loop_status": state.loop_status,
        "continuation_count": metrics["continuation_count"],
        "total_token_estimate": metrics["token_estimate"],
        "last_checkpoint_at": metrics["last_checkpoint_at"],
        "breaker_config": {
            "max_continuations": state.max_continuations,
            "max_wall_clock_seconds": state.max_wall_clock_seconds,
            "max_token_estimate": state.max_token_estimate,
            "idle_timeout_seconds": state.idle_timeout_seconds,
        },
    }


async def _ensure_loop_state(instance_id: str, db) -> InstanceLoopState:
    """Lazy-create an active loop state when an instance has no row."""
    from sqlalchemy import select  # local import keeps top-level tight

    result = await db.execute(
        select(InstanceLoopState).where(
            InstanceLoopState.instance_id == instance_id,
            InstanceLoopState.deleted_at.is_(None),
        )
    )
    state = result.scalars().first()
    if state is not None:
        return state
    state = InstanceLoopState(instance_id=instance_id)
    db.add(state)
    await db.flush()
    return state


@router.post("/{instance_id}/interrupt", response_model=InstanceLoopStateOut)
async def interrupt_instance(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> InstanceLoopStateOut:
    """Send a kill signal to the agent loop and mark it interrupted."""
    instance = await _get_instance_or_404(instance_id, db)
    await require_workspace_role(db, current_user.user_id, instance.workspace_id, "editor")
    state = await supervisor.handle_interrupt(instance_id, db)
    await db.commit()
    await db.refresh(state)
    return InstanceLoopStateOut.model_validate(_to_status_payload(state))


@router.post("/{instance_id}/pause", response_model=InstanceLoopStateOut)
async def pause_instance(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> InstanceLoopStateOut:
    """Pause the agent loop and mark its loop state paused."""
    instance = await _get_instance_or_404(instance_id, db)
    await require_workspace_role(db, current_user.user_id, instance.workspace_id, "editor")
    state = await supervisor.handle_pause(instance_id, db)
    await db.commit()
    await db.refresh(state)
    return InstanceLoopStateOut.model_validate(_to_status_payload(state))


@router.post("/{instance_id}/resume", response_model=InstanceLoopStateOut)
async def resume_instance(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> InstanceLoopStateOut:
    """Resume the agent loop and ensure its runtime task is started."""
    instance = await _get_instance_or_404(instance_id, db)
    await require_workspace_role(db, current_user.user_id, instance.workspace_id, "editor")
    state = await supervisor.handle_resume(instance_id, db)
    await db.commit()
    await db.refresh(state)
    await start_runtime_for(instance_id)
    return InstanceLoopStateOut.model_validate(_to_status_payload(state))


@router.get("/{instance_id}/status", response_model=InstanceLoopStateOut)
async def get_instance_status(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> InstanceLoopStateOut:
    """Return the persisted loop state merged with live supervisor metrics."""
    instance = await _get_instance_or_404(instance_id, db)
    await require_workspace_role(db, current_user.user_id, instance.workspace_id, "editor")
    state = await _ensure_loop_state(instance_id, db)
    return InstanceLoopStateOut.model_validate(_to_status_payload(state))


@router.post("/{instance_id}/snapshot", response_model=BoulderSnapshotOut)
async def snapshot_instance(
    instance_id: str,
    db: DB,
    current_user: CurrentUserDep,
) -> BoulderSnapshotOut:
    """Capture and validate the current Boulder snapshot."""
    instance = await _get_instance_or_404(instance_id, db)
    await require_workspace_role(db, current_user.user_id, instance.workspace_id, "editor")
    snapshot, continuation_count, captured_at = await supervisor.capture_snapshot(
        instance_id, db
    )
    return BoulderSnapshotOut(
        boulder_snapshot=snapshot,
        continuation_count=continuation_count,
        captured_at=captured_at,
    )
