"""v4.3 lane 6 — cerebellum_agents → Entity(is_cerebellum) + Instance.

Covers the §6.3 migration algorithm, §8.8 tiebreak, the workspace-create
hook switch, the central_hubs cerebellum read/write path switch, and the
``is_cerebellum`` entity create/update/list surface.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from starlette.testclient import TestClient

from app.core.cerebellum_migration import migrate_cerebellum
from app.models.central_hub import CentralHub, CerebellumAgent
from app.models.entity import Entity
from app.models.event import Event
from app.models.instance import Instance
from app.models.organization import Namespace
from app.models.workspace import Workspace


def _register(client: TestClient, username: str, email: str) -> str:
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": "password123"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_ws_with_agent(
    session: AsyncSession,
    namespace: Namespace,
    *,
    slug: str | None = None,
    loop_status: str = "idle",
    heartbeat_at: datetime | None = None,
    name: str = "cerebellum",
    base_slug: str = "cerebellum-baseclass",
    system_prompt: str | None = None,
    created_at: datetime | None = None,
) -> tuple[Workspace, CerebellumAgent]:
    """Create a Workspace + CentralHub + legacy CerebellumAgent row."""
    ws = Workspace(
        namespace_id=namespace.id,
        name=f"WS {slug or uuid.uuid4().hex[:6]}",
        slug=slug or f"ws-{uuid.uuid4().hex[:8]}",
    )
    session.add(ws)
    await session.flush()
    hub = CentralHub(workspace_id=ws.id)
    session.add(hub)
    await session.flush()
    kwargs = {
        "central_hub_id": hub.id,
        "name": name,
        "base_slug": base_slug,
        "loop_status": loop_status,
        "heartbeat_at": heartbeat_at,
        "system_prompt": system_prompt,
    }
    if created_at is not None:
        kwargs["created_at"] = created_at
    agent = CerebellumAgent(**kwargs)
    session.add(agent)
    await session.flush()
    return ws, agent


async def _run_migration(db_url: str) -> dict:
    engine = create_async_engine(db_url)
    try:
        async with engine.connect() as conn:
            result = await conn.run_sync(migrate_cerebellum)
            await conn.commit()
    finally:
        await engine.dispose()
    return result


# ---------------------------------------------------------------------------
# Baseline characterization (flipped after the workspace-create hook switch).
# ---------------------------------------------------------------------------


class TestWorkspaceCreateBaseline:
    @pytest.mark.asyncio
    async def test_workspace_create_creates_legacy_cerebellum_row(
        self, client: TestClient, session: AsyncSession
    ) -> None:
        token = _register(client, "cb-baseline", "cb-baseline@t.co")
        resp = client.post(
            "/api/v1/workspaces",
            headers=_h(token),
            json={"slug": "cb-baseline-ws", "name": "CB Baseline"},
        )
        assert resp.status_code == 201, resp.text
        # v4.3: the legacy table is no longer written on workspace create.
        agents = (
            await session.execute(
                select(CerebellumAgent).where(CerebellumAgent.deleted_at.is_(None))
            )
        ).scalars().all()
        assert len(agents) == 0


# ---------------------------------------------------------------------------
# §6.3 migration algorithm
# ---------------------------------------------------------------------------


class TestCerebellumMigration:
    @pytest.mark.asyncio
    async def test_migration_creates_entity_and_instance(
        self,
        session: AsyncSession,
        db_url: str,
        namespace_factory,
    ) -> None:
        ns = await namespace_factory(slug="mig-1")
        ws, agent = await _make_ws_with_agent(
            session, ns, system_prompt="Be wise, little brain"
        )
        await session.commit()

        report = await _run_migration(db_url)
        assert report["entities_created"] == 1
        assert report["instances_created"] == 1
        assert report["merged"] == 0

        entity = (
            await session.execute(
                select(Entity).where(
                    Entity.namespace_id == ns.id,
                    Entity.is_cerebellum.is_(True),
                    Entity.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        assert entity.slug == "cerebellum"
        assert entity.name == "cerebellum"
        assert entity.preset_slug == "cerebellum-baseclass"
        assert entity.system_prompt == "Be wise, little brain"

        instance = (
            await session.execute(
                select(Instance).where(
                    Instance.entity_id == entity.id,
                    Instance.workspace_id == ws.id,
                    Instance.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        assert instance.status == "running"  # legacy idle → infra running

        await session.refresh(agent)
        assert agent.deleted_at is not None  # soft-deleted, not removed

    @pytest.mark.asyncio
    async def test_migration_uses_agent_name_and_base_slug(
        self,
        session: AsyncSession,
        db_url: str,
        namespace_factory,
    ) -> None:
        ns = await namespace_factory(slug="mig-2")
        await _make_ws_with_agent(
            session, ns, name="Stratum", base_slug="strategist", loop_status="running"
        )
        await session.commit()
        await _run_migration(db_url)

        entity = (
            await session.execute(
                select(Entity).where(
                    Entity.namespace_id == ns.id,
                    Entity.is_cerebellum.is_(True),
                )
            )
        ).scalar_one()
        assert entity.name == "Stratum"
        assert entity.preset_slug == "strategist"
        instance = (
            await session.execute(
                select(Instance).where(Instance.entity_id == entity.id)
            )
        ).scalar_one()
        assert instance.status == "running"

    @pytest.mark.asyncio
    async def test_migration_handles_unique_slug_collision(
        self,
        session: AsyncSession,
        db_url: str,
        entity_factory,
        namespace_factory,
    ) -> None:
        ns = await namespace_factory(slug="mig-3")
        await entity_factory(namespace_id=ns.id, slug="cerebellum", name="Occupied")
        ws, _ = await _make_ws_with_agent(session, ns)
        await session.commit()
        await _run_migration(db_url)

        entity = (
            await session.execute(
                select(Entity).where(
                    Entity.namespace_id == ns.id,
                    Entity.is_cerebellum.is_(True),
                )
            )
        ).scalar_one()
        assert entity.slug.startswith("cerebellum-")
        assert entity.slug != "cerebellum"
        instance = (
            await session.execute(
                select(Instance).where(
                    Instance.entity_id == entity.id,
                    Instance.workspace_id == ws.id,
                )
            )
        ).scalar_one()
        assert instance is not None

    @pytest.mark.asyncio
    async def test_migration_is_idempotent(
        self,
        session: AsyncSession,
        db_url: str,
        namespace_factory,
    ) -> None:
        ns = await namespace_factory(slug="mig-idem")
        ws, agent = await _make_ws_with_agent(session, ns)
        await session.commit()

        first = await _run_migration(db_url)
        second = await _run_migration(db_url)
        assert first["entities_created"] == 1
        assert second["entities_created"] == 0  # already migrated → no dupes
        assert second["instances_created"] == 0

        entities = (
            await session.execute(
                select(Entity).where(
                    Entity.namespace_id == ns.id,
                    Entity.is_cerebellum.is_(True),
                    Entity.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        assert len(entities) == 1
        instances = (
            await session.execute(
                select(Instance).where(
                    Instance.entity_id == entities[0].id,
                    Instance.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        assert len(instances) == 1

    @pytest.mark.asyncio
    async def test_migration_merge_case_does_not_duplicate_entity(
        self,
        session: AsyncSession,
        db_url: str,
        namespace_factory,
    ) -> None:
        ns = await namespace_factory(slug="mig-merge")
        ws_a, agent_a = await _make_ws_with_agent(
            session,
            ns,
            slug="ws-a",
            heartbeat_at=datetime.now(timezone.utc) - timedelta(hours=2),
            name="Old",
        )
        ws_b, agent_b = await _make_ws_with_agent(
            session,
            ns,
            slug="ws-b",
            heartbeat_at=datetime.now(timezone.utc),
            name="New",
            system_prompt="newest prompt",
        )
        await session.commit()

        report = await _run_migration(db_url)
        assert report["entities_created"] == 1
        assert report["instances_created"] == 2
        assert report["merged"] == 1

        entities = (
            await session.execute(
                select(Entity).where(
                    Entity.namespace_id == ns.id,
                    Entity.is_cerebellum.is_(True),
                    Entity.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        assert len(entities) == 1
        # winner is the newest heartbeat → its identity wins
        assert entities[0].name == "New"
        assert entities[0].system_prompt == "newest prompt"

        for ws in (ws_a, ws_b):
            inst = (
                await session.execute(
                    select(Instance).where(
                        Instance.entity_id == entities[0].id,
                        Instance.workspace_id == ws.id,
                        Instance.deleted_at.is_(None),
                    )
                )
            ).scalar_one()
            assert inst is not None

        # §6.3: conflict → cerebellum.migration_merged event
        events = (
            await session.execute(
                select(Event).where(Event.type == "cerebellum.migration_merged")
            )
        ).scalars().all()
        assert len(events) == 1
        assert events[0].payload["agent_id"] == agent_a.id

        await session.refresh(agent_a)
        await session.refresh(agent_b)
        assert agent_a.deleted_at is not None
        assert agent_b.deleted_at is not None

    @pytest.mark.asyncio
    async def test_migration_tiebreak_uses_heartbeat_created_id(
        self,
        session: AsyncSession,
        db_url: str,
        namespace_factory,
    ) -> None:
        ns = await namespace_factory(slug="mig-tie")
        now = datetime.now(timezone.utc)
        # §8.8: heartbeat_at desc → created_at desc → id desc
        _, agent_old = await _make_ws_with_agent(
            session,
            ns,
            slug="tie-old",
            name="OlderBeat",
            heartbeat_at=now - timedelta(minutes=1),
        )
        _, agent_new = await _make_ws_with_agent(
            session,
            ns,
            slug="tie-new",
            name="NewerBeat",
            heartbeat_at=now,
            system_prompt="winner prompt",
        )
        await session.commit()
        await _run_migration(db_url)

        entity = (
            await session.execute(
                select(Entity).where(
                    Entity.namespace_id == ns.id,
                    Entity.is_cerebellum.is_(True),
                )
            )
        ).scalar_one()
        assert entity.name == "NewerBeat"
        assert entity.system_prompt == "winner prompt"

    @pytest.mark.asyncio
    async def test_migration_backfills_empty_prompt_but_never_overwrites(
        self,
        session: AsyncSession,
        db_url: str,
        entity_factory,
        namespace_factory,
    ) -> None:
        ns = await namespace_factory(slug="mig-prompt")
        # existing cerebellum entity with an EMPTY prompt → backfill
        existing = await entity_factory(
            namespace_id=ns.id,
            slug="cerebellum",
            name="Existing Cerebellum",
            is_cerebellum=True,
            system_prompt=None,
        )
        ws, agent = await _make_ws_with_agent(
            session, ns, system_prompt="backfilled prompt"
        )
        await session.commit()
        await _run_migration(db_url)

        await session.refresh(existing)
        assert existing.system_prompt == "backfilled prompt"

        # now a NON-empty prompt on a second namespace must not be overwritten
        ns2 = await namespace_factory(slug="mig-prompt2")
        existing2 = await entity_factory(
            namespace_id=ns2.id,
            slug="cerebellum",
            name="Kept",
            is_cerebellum=True,
            system_prompt="hands off",
        )
        await _make_ws_with_agent(session, ns2, system_prompt="agent prompt")
        await session.commit()
        await _run_migration(db_url)
        await session.refresh(existing2)
        assert existing2.system_prompt == "hands off"

    @pytest.mark.asyncio
    async def test_migration_leaves_orphaned_agent_untouched(
        self,
        session: AsyncSession,
        db_url: str,
        namespace_factory,
    ) -> None:
        """Agent whose hub/workspace is soft-deleted is skipped (logged)."""
        ns = await namespace_factory(slug="mig-orphan")
        ws, agent = await _make_ws_with_agent(session, ns, slug="orphan-ws")
        hub = await session.get(CentralHub, agent.central_hub_id)
        assert hub is not None
        hub.soft_delete()
        ws.soft_delete()
        await session.commit()
        report = await _run_migration(db_url)
        assert report["scanned"] == 1
        assert report["instances_created"] == 0
        await session.refresh(agent)
        assert agent.deleted_at is None


# ---------------------------------------------------------------------------
# Workspace-create hook switch + central_hubs read/write path
# ---------------------------------------------------------------------------


class TestWorkspaceCreateSwitch:
    @pytest.mark.asyncio
    async def test_workspace_create_no_legacy_row_and_cerebellum_entity(
        self, client: TestClient, session: AsyncSession
    ) -> None:
        token = _register(client, "cb-switch", "cb-switch@t.co")
        resp = client.post(
            "/api/v1/workspaces",
            headers=_h(token),
            json={"slug": "cb-switch-ws", "name": "CB Switch"},
        )
        assert resp.status_code == 201, resp.text

        # No legacy table writes anymore.
        agents = (
            await session.execute(
                select(CerebellumAgent).where(CerebellumAgent.deleted_at.is_(None))
            )
        ).scalars().all()
        assert len(agents) == 0

        # The cerebellum is now an Entity + Instance.
        entities = (
            await session.execute(
                select(Entity).where(Entity.is_cerebellum.is_(True))
            )
        ).scalars().all()
        assert len(entities) == 1
        assert entities[0].slug == "cerebellum"
        assert entities[0].is_cerebellum is True
        instances = (
            await session.execute(
                select(Instance).where(Instance.entity_id == entities[0].id)
            )
        ).scalars().all()
        assert len(instances) == 1


class TestCentralHubsCerebellum:
    @pytest.mark.asyncio
    async def test_get_patch_restart_operate_on_entity_instance(
        self, client: TestClient, session: AsyncSession
    ) -> None:
        token = _register(client, "cb-chub", "cb-chub@t.co")
        wid = client.post(
            "/api/v1/workspaces",
            headers=_h(token),
            json={"slug": "cb-chub-ws", "name": "CB Hub"},
        ).json()["id"]

        get = client.get(f"/api/v1/central-hubs/{wid}/cerebellum", headers=_h(token))
        assert get.status_code == 200, get.text
        body = get.json()
        assert body["slug"] == "cerebellum"
        assert body["status"] == "creating"
        assert body["workspace_id"] == wid
        assert body["entity_id"]
        assert body["instance_id"]

        patch = client.patch(
            f"/api/v1/central-hubs/{wid}/cerebellum",
            headers=_h(token),
            json={"name": "Renamed Cerebellum", "system_prompt": "Think deeper"},
        )
        assert patch.status_code == 200, patch.text
        assert patch.json()["name"] == "Renamed Cerebellum"
        assert patch.json()["system_prompt"] == "Think deeper"

        restart = client.post(
            f"/api/v1/central-hubs/{wid}/cerebellum/restart",
            headers=_h(token),
        )
        assert restart.status_code == 200, restart.text
        # v4.9.1 real restart: response mirrors the re-deploy pipeline.
        restart_body = restart.json()
        assert restart_body["status"] in {"deploying", "failed"}
        assert restart_body["entity_id"] == body["entity_id"]
        assert restart_body["instance_id"] == body["instance_id"]
        assert "restarted_at" in restart_body

        entity = await session.get(Entity, body["entity_id"])
        assert entity is not None
        assert entity.name == "Renamed Cerebellum"
        assert entity.system_prompt == "Think deeper"
        instance = await session.get(Instance, body["instance_id"])
        assert instance is not None
        assert instance.status in {
            "deploying",
            "failed",
            "running",
            "restarting",
        }
        assert instance.active_hash == entity.migration_hash


# ---------------------------------------------------------------------------
# is_cerebellum on the entity API surface
# ---------------------------------------------------------------------------


class TestEntityIsCerebellum:
    def _new_ns(self, client: TestClient, token: str) -> str:
        resp = client.post(
            "/api/v1/namespaces",
            headers=_h(token),
            json={"slug": f"cb-{uuid.uuid4().hex[:8]}", "name": "CB NS"},
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    @pytest.mark.asyncio
    async def test_create_and_update_accept_is_cerebellum(
        self, client: TestClient, session: AsyncSession
    ) -> None:
        token = _register(client, "cb-ent", "cb-ent@t.co")
        ns_id = self._new_ns(client, token)
        resp = client.post(
            "/api/v1/entities",
            headers=_h(token),
            json={
                "slug": "cb-main",
                "name": "Cerebellum Main",
                "namespace_id": ns_id,
                "is_cerebellum": True,
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["is_cerebellum"] is True
        entity_id = resp.json()["id"]

        row = await session.get(Entity, entity_id)
        assert row is not None
        assert row.is_cerebellum is True  # real DB row, not just HTTP 200

        upd = client.patch(
            f"/api/v1/entities/{entity_id}",
            headers=_h(token),
            json={"is_cerebellum": False},
        )
        assert upd.status_code == 200, upd.text
        assert upd.json()["is_cerebellum"] is False

    def test_create_second_cerebellum_in_same_ns_conflicts(
        self, client: TestClient
    ) -> None:
        token = _register(client, "cb-conflict", "cb-conflict@t.co")
        ns_id = self._new_ns(client, token)
        first = client.post(
            "/api/v1/entities",
            headers=_h(token),
            json={
                "slug": "cb-one",
                "name": "Cerebellum One",
                "namespace_id": ns_id,
                "is_cerebellum": True,
            },
        )
        assert first.status_code == 201, first.text
        second = client.post(
            "/api/v1/entities",
            headers=_h(token),
            json={
                "slug": "cb-two",
                "name": "Cerebellum Two",
                "namespace_id": ns_id,
                "is_cerebellum": True,
            },
        )
        assert second.status_code == 409, second.text
        assert second.json()["error_code"] == "entity.cerebellum_already_exists"

    def test_list_filters_by_is_cerebellum(self, client: TestClient) -> None:
        token = _register(client, "cb-list", "cb-list@t.co")
        ns_id = self._new_ns(client, token)
        normal = client.post(
            "/api/v1/entities",
            headers=_h(token),
            json={"slug": "plain", "name": "Plain", "namespace_id": ns_id},
        )
        assert normal.status_code == 201, normal.text
        cb = client.post(
            "/api/v1/entities",
            headers=_h(token),
            json={
                "slug": "cb-flag",
                "name": "Flagged",
                "namespace_id": ns_id,
                "is_cerebellum": True,
            },
        )
        assert cb.status_code == 201, cb.text

        only_cb = client.get(
            f"/api/v1/entities?is_cerebellum=true&namespace_id={ns_id}",
            headers=_h(token),
        )
        assert only_cb.status_code == 200
        cb_slugs = {i["slug"] for i in only_cb.json()["items"]}
        assert cb_slugs == {"cb-flag"}

        only_plain = client.get(
            f"/api/v1/entities?is_cerebellum=false&namespace_id={ns_id}",
            headers=_h(token),
        )
        assert only_plain.status_code == 200
        plain_slugs = {i["slug"] for i in only_plain.json()["items"]}
        assert plain_slugs == {"plain"}
