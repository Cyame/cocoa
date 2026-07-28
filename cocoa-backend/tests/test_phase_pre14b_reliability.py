"""pre-14b Wave 2: deploy_service reliability helpers integration tests."""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app.models.deploy_record import DeployRecord
from app.services.deploy_service import (
    PROGRESS_STEP_NAMES,
    _TASK_REGISTRY,
    _dump_deploy_config_snapshot,
    _extract_progress_step_names,
    _load_deploy_config_snapshot,
    _restore_agent_bundle_with_retry,
    _set_progress_step_names,
    _unregister_deploy_task,
    cancel_deploy_task,
    register_deploy_task,
)


@pytest.mark.asyncio
async def test_task_registry_register_unregister() -> None:
    task = asyncio.create_task(asyncio.sleep(0.01))
    register_deploy_task("rec-1", task)
    assert "rec-1" in _TASK_REGISTRY
    _unregister_deploy_task("rec-1")
    assert "rec-1" not in _TASK_REGISTRY
    task.cancel()


@pytest.mark.asyncio
async def test_cancel_deploy_task_returns_true_when_pending() -> None:
    async def pending() -> None:
        await asyncio.sleep(10)

    task = asyncio.create_task(pending())
    register_deploy_task("rec-pending", task)
    assert cancel_deploy_task("rec-pending") is True


@pytest.mark.asyncio
async def test_cancel_deploy_task_returns_false_when_done() -> None:
    async def quick() -> str:
        return "done"

    task = asyncio.create_task(quick())
    await task
    register_deploy_task("rec-done", task)
    assert cancel_deploy_task("rec-done") is False


def test_config_snapshot_round_trip() -> None:
    snapshot = {"instance_id": "abc", "image_version": "v1", "cpu_limit": "500m"}
    record = MagicMock(spec=DeployRecord)
    record.config_snapshot = _dump_deploy_config_snapshot(snapshot)
    assert _load_deploy_config_snapshot(record) == snapshot


def test_config_snapshot_empty_returns_dict() -> None:
    record = MagicMock(spec=DeployRecord)
    record.config_snapshot = None
    assert _load_deploy_config_snapshot(record) == {}


def test_step_names_persistence_via_message() -> None:
    record = MagicMock(spec=DeployRecord)
    record.message = None
    _set_progress_step_names(record, PROGRESS_STEP_NAMES)
    assert _extract_progress_step_names(record) == PROGRESS_STEP_NAMES


def test_step_names_preserves_existing_message() -> None:
    record = MagicMock(spec=DeployRecord)
    record.message = json.dumps({"user_note": "test"})
    _set_progress_step_names(record, ["step1"])
    data = json.loads(record.message)
    assert data["user_note"] == "test"
    assert data["steps"] == ["step1"]


@pytest.mark.asyncio
async def test_agent_bundle_retry_succeeds() -> None:
    result = await _restore_agent_bundle_with_retry(MagicMock(), max_retries=3)
    assert result is True


@pytest.mark.asyncio
async def test_agent_bundle_retry_accepts_max_retries() -> None:
    result = await _restore_agent_bundle_with_retry(MagicMock(), max_retries=2)
    assert result is True


@pytest.mark.asyncio
async def test_pipeline_cancellation_via_task_registry() -> None:
    async def long_running() -> None:
        await asyncio.sleep(10)

    task = asyncio.create_task(long_running())
    register_deploy_task("rec-cancel", task)
    assert cancel_deploy_task("rec-cancel") is True
