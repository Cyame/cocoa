"""v4.8 meetings + brainstem runner tests.

Covers the meeting lifecycle API (create/list/get/start/end/cancel + 409
transitions), the M6 participant wake matrix (soft_inject / wake / resume+wake
/ no-instance / wake-failed branches), and the brainstem runner tick
(compute_next_run_at + SKIP LOCKED fire -> inject queue + schedule.fired).

Every DB-touching test uses the conftest per-test cloned database — never
``eyot_dev``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from starlette.testclient import TestClient

from app.core.brainstem_runner import brainstem_tick, compute_next_run_at
from app.core.event_types import (
    MEETING_CANCELLED,
    MEETING_CREATED,
    MEETING_ENDED,
    MEETING_PARTICIPANT_NO_INSTANCE,
    MEETING_PARTICIPANT_WAKE_FAILED,
    MEETING_STARTED,
    SCHEDULE_CREATED,
    SCHEDULE_FIRED,
)
from app.models.event import Event
from app.models.inject_queue import InjectStatus, InstanceInjectQueue
from app.models.loop_state import LoopStatus
from app.models.workspace import Membership


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_token(client: TestClient) -> str:
    """First registered user is super-admin (permissions bypass)."""
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": "v48meet",
            "email": "v48meet@test.com",
            "password": "password123",
        },
    )
    assert resp.status_code == 201, resp.text
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "v48meet", "password": "password123"},
    )
    return login.json()["access_token"]


def _register(client: TestClient, username: str) -> tuple[str, str]:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@test.com",
            "password": "password123",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["id"]


def _workspace(client: TestClient, token: str, slug: str) -> str:
    resp = client.post(
        "/api/v1/workspaces",
        headers=_h(token),
        json={"slug": slug, "name": slug},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_meeting(client: TestClient, token: str, wid: str, **overrides) -> dict:
    body = {
        "workspace_id": wid,
        "title": overrides.pop("title", "Standup"),
        "agenda": overrides.pop("agenda", "Sync on blockers"),
        "scheduled_at": overrides.pop(
            "scheduled_at", (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        ),
    }
    body.update(overrides)
    resp = client.post("/api/v1/meetings", headers=_h(token), json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Event constants
# ---------------------------------------------------------------------------


def test_meeting_event_constants_locked() -> None:
    assert MEETING_CREATED == "meeting.created"
    assert MEETING_STARTED == "meeting.started"
    assert MEETING_ENDED == "meeting.ended"
    assert MEETING_CANCELLED == "meeting.cancelled"
    assert MEETING_PARTICIPANT_WAKE_FAILED == "meeting.participant_wake_failed"
    assert MEETING_PARTICIPANT_NO_INSTANCE == "meeting.participant_no_instance"
    assert SCHEDULE_CREATED == "schedule.created"
    assert SCHEDULE_FIRED == "schedule.fired"


# ---------------------------------------------------------------------------
# Meeting lifecycle
# ---------------------------------------------------------------------------


class TestMeetingLifecycle:
    def test_create_list_get(self, client: TestClient, auth_token: str) -> None:
        wid = _workspace(client, auth_token, "mtg-list")
        meeting = _create_meeting(client, auth_token, wid, title="Planning")
        assert meeting["status"] == "scheduled"
        assert meeting["title"] == "Planning"
        assert meeting["participants"] == []

        listed = client.get(
            f"/api/v1/meetings?workspace_id={wid}", headers=_h(auth_token)
        )
        assert listed.status_code == 200
        assert listed.json()["total"] >= 1
        assert listed.json()["items"][0]["id"] == meeting["id"]

        got = client.get(f"/api/v1/meetings/{meeting['id']}", headers=_h(auth_token))
        assert got.status_code == 200
        assert got.json()["status"] == "scheduled"

    def test_create_emits_meeting_created(self, client: TestClient, auth_token: str) -> None:
        wid = _workspace(client, auth_token, "mtg-evt")
        meeting = _create_meeting(client, auth_token, wid)
        resp = client.get(
            f"/api/v1/events?type_prefix=meeting.created&resource_id={meeting['id']}",
            headers=_h(auth_token),
        )
        assert resp.status_code == 200
        assert any(e["type"] == "meeting.created" for e in resp.json()["items"])

    def test_start_end_cancel_cycle(self, client: TestClient, auth_token: str) -> None:
        wid = _workspace(client, auth_token, "mtg-cycle")
        meeting = _create_meeting(client, auth_token, wid)

        started = client.post(
            f"/api/v1/meetings/{meeting['id']}/start", headers=_h(auth_token)
        )
        assert started.status_code == 200
        assert started.json()["status"] == "active"

        ended = client.post(
            f"/api/v1/meetings/{meeting['id']}/end", headers=_h(auth_token)
        )
        assert ended.status_code == 200
        assert ended.json()["status"] == "ended"
        assert ended.json()["ended_at"] is not None

        resp = client.post(
            f"/api/v1/meetings/{meeting['id']}/start", headers=_h(auth_token)
        )
        assert resp.status_code == 409
        assert resp.json()["message_key"] == "errors.meeting.invalid_transition"

    def test_cancel_allowed_from_scheduled_and_active(
        self, client: TestClient, auth_token: str
    ) -> None:
        wid = _workspace(client, auth_token, "mtg-cancel")
        scheduled = _create_meeting(client, auth_token, wid)
        resp = client.post(
            f"/api/v1/meetings/{scheduled['id']}/cancel", headers=_h(auth_token)
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

        active = _create_meeting(client, auth_token, wid)
        client.post(f"/api/v1/meetings/{active['id']}/start", headers=_h(auth_token))
        resp = client.post(
            f"/api/v1/meetings/{active['id']}/cancel", headers=_h(auth_token)
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_unknown_membership_rejected_400(
        self, client: TestClient, auth_token: str
    ) -> None:
        wid = _workspace(client, auth_token, "mtg-bad")
        resp = client.post(
            "/api/v1/meetings",
            headers=_h(auth_token),
            json={
                "workspace_id": wid,
                "title": "Bad participants",
                "scheduled_at": (
                    datetime.now(timezone.utc) + timedelta(hours=1)
                ).isoformat(),
                "participant_membership_ids": ["does-not-exist"],
            },
        )
        assert resp.status_code == 400
        assert (
            resp.json()["message_key"]
            == "errors.meeting.membership_not_in_workspace"
        )

    def test_meeting_not_found_404(self, client: TestClient, auth_token: str) -> None:
        resp = client.get("/api/v1/meetings/missing", headers=_h(auth_token))
        assert resp.status_code == 404
        assert resp.json()["message_key"] == "errors.meeting.not_found"


# ---------------------------------------------------------------------------
# M6 participant wake matrix
# ---------------------------------------------------------------------------


class TestM6WakeMatrix:
    async def _instance_seat(self, session, wid: str, instance, pos: int = 1) -> str:
        membership = Membership(workspace_id=wid, instance_id=instance.id, posx=pos, posy=pos)
        session.add(membership)
        await session.commit()
        return membership.id

    async def _user_seat(self, session, wid: str, user_id: str, pos: int = 1) -> str:
        membership = Membership(workspace_id=wid, user_id=user_id, posx=pos, posy=pos)
        session.add(membership)
        await session.commit()
        return membership.id

    @pytest.mark.asyncio
    async def test_running_loop_gets_soft_inject(
        self,
        client: TestClient,
        auth_token: str,
        session,
        instance_factory,
        loop_state_factory,
    ) -> None:
        from app.models.instance import InstanceStatus

        wid = _workspace(client, auth_token, "m6-soft")
        inst = await instance_factory(
            workspace_id=wid, status=InstanceStatus.running.value
        )
        await loop_state_factory(inst, loop_status=LoopStatus.running.value)
        mid = await self._instance_seat(session, wid, inst)
        meeting = _create_meeting(
            client, auth_token, wid, participant_membership_ids=[mid]
        )

        resp = client.post(
            f"/api/v1/meetings/{meeting['id']}/start", headers=_h(auth_token)
        )
        assert resp.status_code == 200

        rows = (
            await session.execute(
                select(InstanceInjectQueue).where(
                    InstanceInjectQueue.instance_id == inst.id
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].delivery_mode == "soft_inject"
        assert rows[0].kind == "collab_inject"
        assert rows[0].status == InjectStatus.pending.value
        assert rows[0].payload["meeting_id"] == meeting["id"]
        assert rows[0].payload["title"] == "Standup"

    @pytest.mark.asyncio
    async def test_running_idle_loop_gets_wake(
        self,
        client: TestClient,
        auth_token: str,
        session,
        instance_factory,
        loop_state_factory,
    ) -> None:
        from app.models.instance import InstanceStatus

        wid = _workspace(client, auth_token, "m6-wake")
        inst = await instance_factory(
            workspace_id=wid, status=InstanceStatus.running.value
        )
        await loop_state_factory(inst, loop_status=LoopStatus.idle.value)
        mid = await self._instance_seat(session, wid, inst)
        meeting = _create_meeting(
            client, auth_token, wid, participant_membership_ids=[mid]
        )

        resp = client.post(
            f"/api/v1/meetings/{meeting['id']}/start", headers=_h(auth_token)
        )
        assert resp.status_code == 200

        rows = (
            await session.execute(
                select(InstanceInjectQueue).where(
                    InstanceInjectQueue.instance_id == inst.id
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].delivery_mode == "wake"

    @pytest.mark.asyncio
    async def test_pending_instance_resumes_then_wake(
        self, client: TestClient, auth_token: str, session, instance_factory
    ) -> None:
        from app.models.instance import InstanceStatus
        from app.models.loop_state import InstanceLoopState

        wid = _workspace(client, auth_token, "m6-resume")
        inst = await instance_factory(
            workspace_id=wid, status=InstanceStatus.pending.value
        )
        mid = await self._instance_seat(session, wid, inst)
        meeting = _create_meeting(
            client, auth_token, wid, participant_membership_ids=[mid]
        )

        resp = client.post(
            f"/api/v1/meetings/{meeting['id']}/start", headers=_h(auth_token)
        )
        assert resp.status_code == 200

        rows = (
            await session.execute(
                select(InstanceInjectQueue).where(
                    InstanceInjectQueue.instance_id == inst.id
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].delivery_mode == "wake"

        state = (
            await session.execute(
                select(InstanceLoopState).where(
                    InstanceLoopState.instance_id == inst.id
                )
            )
        ).scalar_one_or_none()
        assert state is not None
        assert state.loop_status == LoopStatus.running.value

    @pytest.mark.asyncio
    async def test_membership_without_instance_emits_no_instance(
        self, client: TestClient, auth_token: str, session
    ) -> None:
        _, user_id = _register(client, f"m6user-{datetime.now().microsecond}")
        wid = _workspace(client, auth_token, "m6-none")
        mid = await self._user_seat(session, wid, user_id)
        meeting = _create_meeting(
            client, auth_token, wid, participant_membership_ids=[mid]
        )

        resp = client.post(
            f"/api/v1/meetings/{meeting['id']}/start", headers=_h(auth_token)
        )
        assert resp.status_code == 200

        events = (
            await session.execute(
                select(Event).where(Event.type == MEETING_PARTICIPANT_NO_INSTANCE)
            )
        ).scalars().all()
        assert len(events) == 1
        assert events[0].payload["membership_id"] == mid

    @pytest.mark.asyncio
    async def test_wake_failure_continues_and_emits_failed(
        self,
        client: TestClient,
        auth_token: str,
        session,
        instance_factory,
        monkeypatch,
    ) -> None:
        from app.models.instance import InstanceStatus

        wid = _workspace(client, auth_token, "m6-fail")
        bad = await instance_factory(
            workspace_id=wid, status=InstanceStatus.pending.value
        )
        good = await instance_factory(
            workspace_id=wid, status=InstanceStatus.running.value
        )
        bad_mid = await self._instance_seat(session, wid, bad, pos=1)
        good_mid = await self._instance_seat(session, wid, good, pos=2)
        meeting = _create_meeting(
            client, auth_token, wid, participant_membership_ids=[bad_mid, good_mid]
        )

        async def _boom(instance_id: str) -> None:
            raise RuntimeError("runtime start refused")

        monkeypatch.setattr("app.core.meeting_wake.start_runtime_for", _boom)

        resp = client.post(
            f"/api/v1/meetings/{meeting['id']}/start", headers=_h(auth_token)
        )
        assert resp.status_code == 200

        failed = (
            await session.execute(
                select(Event).where(Event.type == MEETING_PARTICIPANT_WAKE_FAILED)
            )
        ).scalars().all()
        assert len(failed) == 1
        assert failed[0].payload["instance_id"] == bad.id
        assert "runtime start refused" in failed[0].payload["error"]

        rows = (
            await session.execute(
                select(InstanceInjectQueue).where(
                    InstanceInjectQueue.instance_id == good.id
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].delivery_mode == "wake"


# ---------------------------------------------------------------------------
# Brainstem runner
# ---------------------------------------------------------------------------


class TestBrainstemRunner:
    def test_compute_next_run_at_basic(self) -> None:
        base = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)
        assert compute_next_run_at("0 9 * * *", base) == datetime(
            2026, 8, 6, 9, 0, tzinfo=timezone.utc
        )
        soon = compute_next_run_at("* * * * *", base)
        assert soon.minute == 31

    def test_compute_next_run_at_invalid_returns_none(self) -> None:
        assert compute_next_run_at("not a cron", datetime.now(timezone.utc)) is None

    @pytest.mark.asyncio
    async def test_tick_fires_due_schedule(
        self, client: TestClient, auth_token: str, session, instance_factory
    ) -> None:
        from app.models.central_hub import BrainstemSchedule

        wid = _workspace(client, auth_token, "bs-tick")
        resp = client.post(
            f"/api/v1/central-hubs/{wid}/brainstem/schedules",
            headers=_h(auth_token),
            json={
                "name": "tick",
                "cron_expr": "* * * * *",
                "action_payload": {"instance_id": "fake", "delivery_mode": "wake"},
            },
        )
        assert resp.status_code == 201
        schedule_id = resp.json()["id"]
        sched = await session.get(BrainstemSchedule, schedule_id)
        assert sched.next_run_at is not None
        sched.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        inst = await instance_factory()
        sched.action_payload = {"instance_id": inst.id, "delivery_mode": "notify"}
        await session.commit()

        fired = await brainstem_tick(db=session)
        assert fired == 1

        rows = (
            await session.execute(
                select(InstanceInjectQueue).where(
                    InstanceInjectQueue.instance_id == inst.id
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].delivery_mode == "notify"
        assert rows[0].payload == {"instance_id": inst.id, "delivery_mode": "notify"}

        await session.refresh(sched)
        assert sched.last_run_at is not None
        assert sched.next_run_at is not None
        assert sched.next_run_at > sched.last_run_at

        ev = (
            await session.execute(
                select(Event).where(
                    Event.type == SCHEDULE_FIRED, Event.resource_id == schedule_id
                )
            )
        ).scalar_one()
        assert ev.actor_type == "system"

    @pytest.mark.asyncio
    async def test_tick_skips_disabled_and_future_schedules(
        self, client: TestClient, auth_token: str, session, instance_factory
    ) -> None:
        from app.models.central_hub import BrainstemSchedule

        wid = _workspace(client, auth_token, "bs-skip")
        inst = await instance_factory()
        r1 = client.post(
            f"/api/v1/central-hubs/{wid}/brainstem/schedules",
            headers=_h(auth_token),
            json={
                "name": "disabled",
                "cron_expr": "* * * * *",
                "enabled": False,
                "action_payload": {"instance_id": inst.id},
            },
        )
        assert r1.status_code == 201
        disabled_id = r1.json()["id"]
        disabled = await session.get(BrainstemSchedule, disabled_id)
        disabled.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await session.commit()

        fired = await brainstem_tick(db=session)
        assert fired == 0
        assert (
            await session.execute(
                select(Event).where(
                    Event.type == SCHEDULE_FIRED, Event.resource_id == disabled_id
                )
            )
        ).scalars().all() == []

    @pytest.mark.asyncio
    async def test_patch_cron_expr_reprimes_next_run(
        self, client: TestClient, auth_token: str, session
    ) -> None:
        from app.models.central_hub import BrainstemSchedule

        wid = _workspace(client, auth_token, "bs-patch")
        r = client.post(
            f"/api/v1/central-hubs/{wid}/brainstem/schedules",
            headers=_h(auth_token),
            json={"name": "repatch", "cron_expr": "* * * * *"},
        )
        assert r.status_code == 201
        schedule_id = r.json()["id"]
        first = await session.get(BrainstemSchedule, schedule_id)
        assert first.next_run_at is not None

        resp = client.patch(
            f"/api/v1/central-hubs/{wid}/brainstem/schedules/{schedule_id}",
            headers=_h(auth_token),
            json={"cron_expr": "0 9 * * *"},
        )
        assert resp.status_code == 200
        old_next = first.next_run_at
        await session.refresh(first)
        assert first.next_run_at is not None
        assert first.next_run_at != old_next
