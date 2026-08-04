"""v4.7 H6 — inject enqueue chain tests (V47-5 / V47-1 / V47-10).

Covers the three-step downlink surface:

1. Public ``POST /api/v1/instances/{id}/inject`` — 202 + pending row +
   ``harness.inject_requested`` event; 404 for missing instance; 400 for
   the V47-10 tldr rule; 422 for an invalid kind; V47-1 delivery-mode
   derivation (loop state wins, instance status as fallback).
2. ``GET /internal/control/poll`` — returns the pending inject queue items
   (``injects``) alongside the unchanged control ``events`` and marks them
   ``delivered`` (a second poll no longer returns them).
3. ``POST /internal/control/ack`` — acked count + ``harness.inject_applied``
   for soft_inject / wake; no applied event for notify.
4. Safe-point guard — soft-inject is never flushed between a ``tool_use``
   and its ``tool_result`` batch.

Every DB-touching test runs against the per-test cloned database provided
by the conftest ``db_url`` / ``session`` fixtures (``cocoa_dev`` untouched).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.core.event_types import HARNESS_INJECT_APPLIED, HARNESS_INJECT_REQUESTED
from app.models.event import Event
from app.models.inject_queue import InstanceInjectQueue

_TEST_TOKEN = "v47-internal-token"

_INTERNAL_HEADERS = {"Authorization": f"Bearer {_TEST_TOKEN}"}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient) -> tuple[str, str]:
    """Register a fresh user via the public auth endpoint; returns (token, user_id)."""
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": f"v47-{uuid.uuid4().hex[:8]}",
            "email": f"v47-{uuid.uuid4().hex[:8]}@t.co",
            "password": "password123",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["id"]


def _post_inject(
    client: TestClient, instance_id: str, token: str, body: dict
) -> object:
    return client.post(
        f"/api/v1/instances/{instance_id}/inject",
        json=body,
        headers=_auth(token),
    )


async def test_inject_enqueue_returns_202_pending_row_and_event(
    client: TestClient,
    session: AsyncSession,
    workspace_factory,
    instance_factory,
    create_org_bundle,
) -> None:
    """Happy path: 202 + pending queue row + harness.inject_requested event."""
    token, user_id = _register(client)
    ws = await workspace_factory()
    inst = await instance_factory(workspace_id=ws.id, status="running")
    await create_org_bundle(user_id, workspace=ws)

    resp = _post_inject(
        client,
        inst.id,
        token,
        {
            "kind": "gene_inject",
            "delivery_mode": "soft_inject",
            "tldr": "grant capability x",
            "content_refs": [
                {"scope": "hub", "path": "shared/x.md", "label": "x"},
            ],
            "gene_ids": ["gene-1"],
            "capability_ids": ["cap-1"],
        },
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["instance_id"] == inst.id
    assert body["status"] == "pending"
    assert body["delivery_mode"] == "soft_inject"
    queue_id = body["queue_id"]
    assert queue_id

    row = await session.get(InstanceInjectQueue, queue_id)
    assert row is not None
    assert row.status == "pending"
    assert row.kind == "gene_inject"
    assert row.delivery_mode == "soft_inject"
    assert row.payload["gene_ids"] == ["gene-1"]
    assert row.payload["capability_ids"] == ["cap-1"]
    assert row.payload["content_refs"] == [
        {"scope": "hub", "path": "shared/x.md", "label": "x"},
    ]

    result = await session.execute(
        select(Event).where(Event.type == HARNESS_INJECT_REQUESTED)
    )
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].resource_id == inst.id
    assert events[0].payload["queue_id"] == queue_id
    assert events[0].payload["delivery_mode"] == "soft_inject"
    assert events[0].payload["tldr"] == "grant capability x"


async def test_inject_enqueue_404_for_missing_instance(
    client: TestClient, session: AsyncSession
) -> None:
    token, _ = _register(client)
    resp = _post_inject(
        client,
        str(uuid.uuid4()),
        token,
        {"kind": "collab_inject", "delivery_mode": "notify", "tldr": "x"},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error_code"] == "instance.not_found"
    assert resp.json()["message_key"] == "errors.instance.not_found"


async def test_inject_enqueue_422_for_invalid_kind(
    client: TestClient,
    session: AsyncSession,
    workspace_factory,
    instance_factory,
    create_org_bundle,
) -> None:
    token, user_id = _register(client)
    ws = await workspace_factory()
    inst = await instance_factory(workspace_id=ws.id, status="running")
    await create_org_bundle(user_id, workspace=ws)

    resp = _post_inject(
        client,
        inst.id,
        token,
        {"kind": "bogus_kind", "delivery_mode": "notify", "tldr": "x"},
    )
    assert resp.status_code == 422, resp.text


async def test_inject_enqueue_400_when_tldr_required_for_large_report(
    client: TestClient,
    session: AsyncSession,
    workspace_factory,
    instance_factory,
    create_org_bundle,
) -> None:
    """V47-10: prose above 240 chars without a tldr is a hard 400."""
    token, user_id = _register(client)
    ws = await workspace_factory()
    inst = await instance_factory(workspace_id=ws.id, status="running")
    await create_org_bundle(user_id, workspace=ws)

    resp = _post_inject(
        client,
        inst.id,
        token,
        {
            "kind": "collab_inject",
            "delivery_mode": "notify",
            "report": {
                "outcome": "ok",
                "changes": ["x" * 250],
                "validation": [],
                "blockers": [],
            },
        },
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error_code"] == "internal.tldr_required"
    assert resp.json()["message_key"] == "errors.internal.tldr_required"


async def test_delivery_mode_derived_from_state(
    client: TestClient,
    session: AsyncSession,
    workspace_factory,
    entity_factory,
    instance_factory,
    loop_state_factory,
    create_org_bundle,
) -> None:
    """V47-1 default table: explicit mode wins; otherwise derive.

    Loop state is authoritative when present (idle/completed -> wake,
    running -> soft_inject); instance lifecycle status is the fallback
    (running/pending/creating/deploying -> soft_inject, else -> wake).
    """
    token, user_id = _register(client)
    ws = await workspace_factory()

    async def _mk(status: str):
        # One entity per instance: uq_instances_workspace_entity forbids two
        # active instances sharing (workspace_id, entity_id).
        entity = await entity_factory()
        return await instance_factory(
            workspace_id=ws.id, entity_id=entity.id, status=status
        )

    running = await _mk("running")
    pending = await _mk("pending")
    creating = await _mk("creating")
    deploying = await _mk("deploying")
    failed = await _mk("failed")
    loop_idle = await _mk("running")
    await loop_state_factory(loop_idle, loop_status="idle")
    loop_completed = await _mk("running")
    await loop_state_factory(loop_completed, loop_status="completed")
    loop_running = await _mk("running")
    await loop_state_factory(loop_running, loop_status="running")

    # Single commit makes every row visible to the API client's sessions.
    await create_org_bundle(user_id, workspace=ws)

    async def _derived(inst) -> str:
        resp = _post_inject(
            client, inst.id, token, {"kind": "collab_inject", "tldr": "t"}
        )
        assert resp.status_code == 202, resp.text
        return resp.json()["delivery_mode"]

    assert await _derived(running) == "soft_inject"
    assert await _derived(pending) == "soft_inject"
    assert await _derived(creating) == "soft_inject"
    assert await _derived(deploying) == "soft_inject"
    assert await _derived(failed) == "wake"
    assert await _derived(loop_idle) == "wake"
    assert await _derived(loop_completed) == "wake"
    assert await _derived(loop_running) == "soft_inject"


async def test_poll_returns_same_queue_id_and_marks_delivered(
    client: TestClient,
    session: AsyncSession,
    workspace_factory,
    instance_factory,
    create_org_bundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full-chain manual QA: enqueue -> poll returns the SAME queue_id,
    row flips to ``delivered``, and a second poll returns nothing."""
    monkeypatch.setenv("COCOA_API_TOKEN", _TEST_TOKEN)
    token, user_id = _register(client)
    ws = await workspace_factory()
    inst = await instance_factory(workspace_id=ws.id, status="running")
    await create_org_bundle(user_id, workspace=ws)

    resp = _post_inject(
        client,
        inst.id,
        token,
        {
            "kind": "collab_inject",
            "delivery_mode": "soft_inject",
            "tldr": "t",
            "content_refs": [{"scope": "hub", "path": "shared/y.md"}],
        },
    )
    assert resp.status_code == 202, resp.text
    queue_id = resp.json()["queue_id"]

    poll_url = f"/api/v1/internal/control/poll?instance_id={inst.id}&last_seen_id=0"
    poll1 = client.get(poll_url, headers=_INTERNAL_HEADERS)
    assert poll1.status_code == 200, poll1.text
    body = poll1.json()
    # Control events logic untouched: no control events exist here.
    assert body["events"] == []
    assert body["last_seen_id"] == 0
    injects = body["injects"]
    assert len(injects) == 1
    # THE manual-QA assertion: poll returns the queue id the enqueue created.
    assert injects[0]["queue_id"] == queue_id
    assert injects[0]["kind"] == "collab_inject"
    assert injects[0]["delivery_mode"] == "soft_inject"
    assert injects[0]["tldr"] == "t"
    assert injects[0]["payload"]["content_refs"] == [
        {"scope": "hub", "path": "shared/y.md"},
    ]
    assert "expires_at" in injects[0]

    row = await session.get(InstanceInjectQueue, queue_id)
    assert row is not None
    assert row.status == "delivered"

    poll2 = client.get(poll_url, headers=_INTERNAL_HEADERS)
    assert poll2.status_code == 200, poll2.text
    assert poll2.json()["injects"] == []


async def test_ack_returns_count_and_emits_applied(
    client: TestClient,
    session: AsyncSession,
    workspace_factory,
    instance_factory,
    create_org_bundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ack of a delivered soft_inject row -> {acked: 1} + inject_applied event."""
    monkeypatch.setenv("COCOA_API_TOKEN", _TEST_TOKEN)
    token, user_id = _register(client)
    ws = await workspace_factory()
    inst = await instance_factory(workspace_id=ws.id, status="running")
    await create_org_bundle(user_id, workspace=ws)

    resp = _post_inject(
        client,
        inst.id,
        token,
        {"kind": "capability_inject", "delivery_mode": "wake", "tldr": "t"},
    )
    queue_id = resp.json()["queue_id"]
    poll_url = f"/api/v1/internal/control/poll?instance_id={inst.id}&last_seen_id=0"
    poll = client.get(poll_url, headers=_INTERNAL_HEADERS)
    assert poll.json()["injects"][0]["queue_id"] == queue_id

    ack = client.post(
        "/api/v1/internal/control/ack",
        json={"queue_ids": [queue_id]},
        headers=_INTERNAL_HEADERS,
    )
    assert ack.status_code == 200, ack.text
    assert ack.json() == {"acked": 1}

    row = await session.get(InstanceInjectQueue, queue_id)
    assert row is not None
    assert row.status == "acked"
    assert row.acked_at is not None

    result = await session.execute(
        select(Event).where(Event.type == HARNESS_INJECT_APPLIED)
    )
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].resource_id == inst.id
    assert events[0].payload["queue_id"] == queue_id
    assert events[0].payload["delivery_mode"] == "wake"


async def test_ack_notify_mode_emits_no_applied_event(
    client: TestClient,
    session: AsyncSession,
    workspace_factory,
    instance_factory,
    create_org_bundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """notify deliveries are acknowledged without a harness.inject_applied."""
    monkeypatch.setenv("COCOA_API_TOKEN", _TEST_TOKEN)
    token, user_id = _register(client)
    ws = await workspace_factory()
    inst = await instance_factory(workspace_id=ws.id, status="running")
    await create_org_bundle(user_id, workspace=ws)

    resp = _post_inject(
        client,
        inst.id,
        token,
        {"kind": "collab_inject", "delivery_mode": "notify", "tldr": "t"},
    )
    queue_id = resp.json()["queue_id"]
    poll_url = f"/api/v1/internal/control/poll?instance_id={inst.id}&last_seen_id=0"
    poll = client.get(poll_url, headers=_INTERNAL_HEADERS)
    assert poll.json()["injects"][0]["queue_id"] == queue_id

    ack = client.post(
        "/api/v1/internal/control/ack",
        json={"queue_ids": [queue_id]},
        headers=_INTERNAL_HEADERS,
    )
    assert ack.json() == {"acked": 1}

    result = await session.execute(
        select(Event).where(Event.type == HARNESS_INJECT_APPLIED)
    )
    assert result.scalars().all() == []


def test_safe_point_guard_never_flushes_between_tool_use_and_tool_result() -> None:
    """Acceptance: soft-inject is never spliced between tool_use and tool_result."""
    from app.agent_runtime.safe_point import SafePointGuard

    guard = SafePointGuard()
    item = {
        "queue_id": "q1",
        "kind": "collab_inject",
        "delivery_mode": "soft_inject",
        "payload": {"text": "urgent context"},
    }
    guard.hold(item)

    # Provider emits a tool_use block; tool results are now outstanding.
    guard.on_tool_use()
    assert guard.at_safe_point is False
    # Between tool_use and tool_result the guard MUST NOT deliver.
    assert guard.flush() == []
    assert guard.pending_count == 1

    # Tool results arrive; the batch is complete -> the safe point opens.
    guard.on_tool_results()
    assert guard.at_safe_point is True
    delivered = guard.flush()
    assert [d["queue_id"] for d in delivered] == ["q1"]
    assert guard.pending_count == 0

    # A later flush has nothing left to deliver.
    assert guard.flush() == []


def test_safe_point_guard_holds_through_multiple_outstanding_batches() -> None:
    from app.agent_runtime.safe_point import SafePointGuard

    guard = SafePointGuard()
    guard.hold({"queue_id": "q2", "delivery_mode": "wake"})
    guard.on_tool_use()
    guard.on_tool_use()  # two batches outstanding (e.g. parallel tool calls)
    guard.on_tool_results()  # only one batch completed
    assert guard.flush() == []  # still one outstanding batch
    guard.on_tool_results()
    delivered = guard.flush()
    assert [d["queue_id"] for d in delivered] == ["q2"]
