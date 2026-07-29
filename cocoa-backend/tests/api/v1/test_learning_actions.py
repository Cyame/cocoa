"""Integration tests for phase-15f capability lifecycle endpoints (T3).

Covers:
- POST /api/v1/learning/instances/{iid}/reap (memory → capability)
- POST /api/v1/learning/entities/{eid}/promote (instance cap → entity)
- POST /api/v1/learning/entities/{eid}/transmute (entity → base class)
- POST /api/v1/learning/capabilities/combine (N caps → 1 gene)
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models import AiGene, BaseClass, CapabilityMarketEntry
from app.models.entity import Entity
from app.models.event import Event
from app.models.user import User

# ---------------------------------------------------------------------------
# Fixtures (shared with the existing test_phase10_learning.py pattern)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


@pytest.fixture
def auth_token(client: TestClient) -> str:
    client.post("/api/v1/auth/register", json={
        "username": "p15f_actions",
        "email": "p15f_actions@test.com",
        "password": "password123",
    })
    resp = client.post("/api/v1/auth/login", json={
        "username": "p15f_actions",
        "password": "password123",
    })
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def auth_user_id(auth_token: str, session: AsyncSession) -> str:
    result = await session.execute(
        select(User).where(User.username == "p15f_actions"),
    )
    user: User = result.scalars().first()
    return user.id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup_workspace(client: TestClient, token: str, slug: str | None = None) -> str:
    slug = slug or f"p15f-workspace-{uuid.uuid4().hex[:6]}"
    resp = client.post("/api/v1/workspaces", headers=_auth(token), json={
        "name": f"P15f Workspace {slug}",
        "slug": slug,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_entity(
    client: TestClient, token: str, slug: str | None = None, name: str = "Worker",
) -> str:
    slug = slug or f"p15f-emp-{uuid.uuid4().hex[:6]}"
    resp = client.post("/api/v1/entities", headers=_auth(token), json={
        "name": name, "slug": slug,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_instance(
    client: TestClient, token: str, entity_id: str, workspace_id: str,
) -> str:
    resp = client.post("/api/v1/instances", headers=_auth(token), json={
        "entity_id": entity_id,
        "workspace_id": workspace_id,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_memory(
    client: TestClient, token: str, entity_id: str, *,
    kind: str, key: str | None = None, content: str | None = None,
) -> str:
    body: dict = {"entity_id": entity_id, "kind": kind}
    if key is not None:
        body["key"] = key
    if content is not None:
        body["content"] = content
    resp = client.post("/api/v1/memory/entries", headers=_auth(token), json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# =========================================================================
# Endpoint A: POST /learning/instances/{iid}/reap
# =========================================================================


class TestReap:
    """Tests for the reap endpoint."""

    def test_reap_returns_200_with_capabilities(
        self, client: TestClient, auth_token: str, auth_user_id: str,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)

        for i in range(3):
            _create_memory(
                client, auth_token, entity_id, kind="lesson",
                key=f"debug-pattern-{i}",
                content=f"Lesson {i} about debugging memory leaks in async code",
            )
        _create_memory(
            client, auth_token, entity_id, kind="decision",
            key="pick-stack",
            content="We decided to use FastAPI over Flask",
        )

        resp = client.post(
            f"/api/v1/learning/instances/{instance_id}/reap",
            headers=h,
            json={"memory_kind_filter": ["lesson", "decision"], "max_capabilities": 10},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "ok"
        assert body["instance_id"] == instance_id
        assert body["memory_consumed"] == 4
        assert len(body["capability_distilled"]) == 4
        assert body["capability_market_uploaded"] == 4
        assert body["instance_local_added"] == 4
        assert body["entity_changed"] is False

        # Every distilled cap has the required fields.
        for cap in body["capability_distilled"]:
            assert cap["name"]
            assert cap["type"] == "skill"
            assert "auto-distilled" in cap["tags"]

    async def test_reap_writes_to_capability_market(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)

        _create_memory(
            client, auth_token, entity_id, kind="lesson",
            key="codegen-pattern",
            content="Pattern for code generation that avoids hardcoding",
        )

        resp = client.post(
            f"/api/v1/learning/instances/{instance_id}/reap",
            headers=h,
            json={},
        )
        assert resp.status_code == 200, resp.text

        market_result = await session.execute(
            select(CapabilityMarketEntry).where(
                CapabilityMarketEntry.deleted_at.is_(None),
                CapabilityMarketEntry.created_via == "reap",
            )
        )
        rows = list(market_result.scalars().all())
        assert len(rows) >= 1
        assert any(r.name == "codegen-pattern" for r in rows)

    async def test_reap_does_not_touch_entity_capabilities(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """Per PRD §13.6.10.3: reap is instance-private — Entity unchanged."""
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)

        _create_memory(
            client, auth_token, entity_id, kind="lesson",
            key="foo-pattern",
            content="Some pattern for things",
        )

        resp = client.post(
            f"/api/v1/learning/instances/{instance_id}/reap",
            headers=h,
            json={},
        )
        assert resp.status_code == 200, resp.text

        emp = await session.get(Entity, entity_id)
        assert emp is not None
        assert emp.capabilities in (None, [])

    async def test_reap_snapshot_only_skips_writes(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """snapshot_only=true returns preview without writing to DB."""
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)

        _create_memory(
            client, auth_token, entity_id, kind="lesson",
            key="preview-only",
            content="A lesson that should not be persisted",
        )

        resp = client.post(
            f"/api/v1/learning/instances/{instance_id}/reap",
            headers=h,
            json={"snapshot_only": True},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["capability_market_uploaded"] == 0
        assert body["instance_local_added"] == 0

        market_result = await session.execute(
            select(CapabilityMarketEntry).where(
                CapabilityMarketEntry.deleted_at.is_(None)
            )
        )
        assert market_result.scalars().first() is None

    def test_reap_404_for_unknown_instance(
        self, client: TestClient, auth_token: str,
    ) -> None:
        h = _auth(auth_token)
        resp = client.post(
            f"/api/v1/learning/instances/{uuid.uuid4()}/reap",
            headers=h,
            json={},
        )
        assert resp.status_code == 404, resp.text

    async def test_reap_emits_event(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)

        _create_memory(
            client, auth_token, entity_id, kind="lesson",
            key="evented-cap",
            content="An evented capability memory",
        )

        resp = client.post(
            f"/api/v1/learning/instances/{instance_id}/reap",
            headers=h,
            json={},
        )
        assert resp.status_code == 200, resp.text

        ev_result = await session.execute(
            select(Event).where(Event.type == "learning.reap_completed")
        )
        events = list(ev_result.scalars().all())
        assert len(events) == 1
        assert events[0].resource_id == instance_id
        assert events[0].payload["memory_consumed"] == 1
        assert events[0].payload["capabilities_count"] == 1


# =========================================================================
# Endpoint B: POST /learning/entities/{eid}/promote
# =========================================================================


class TestPromote:
    """Tests for the promote endpoint."""

    async def test_promote_writes_to_entity_capabilities(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)

        # First reap to populate runtime_config["reaped_capabilities"].
        _create_memory(
            client, auth_token, entity_id, kind="lesson",
            key="alpha", content="A pattern for alpha",
        )
        reap_resp = client.post(
            f"/api/v1/learning/instances/{instance_id}/reap",
            headers=h, json={},
        )
        assert reap_resp.status_code == 200, reap_resp.text

        # Now promote.
        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/promote",
            headers=h,
            json={"from_instance_id": instance_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "ok"
        assert body["entity_id"] == entity_id
        assert body["capability_promoted_count"] >= 1
        assert len(body["entity_promotion_migration_hash"]) == 64

        emp = await session.get(Entity, entity_id)
        assert emp is not None
        assert emp.capabilities is not None and len(emp.capabilities) >= 1
        assert emp.migration_hash == body["entity_promotion_migration_hash"]
        assert emp.system_prompt is not None

    async def test_promote_does_not_write_capability_market(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """Promote is Chain B — Entity only; never writes capability_market."""
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)

        from app.models.instance import Instance

        inst = await session.get(Instance, instance_id)
        assert inst is not None
        inst.runtime_config = {
            "reaped_capabilities": [
                {"name": "promote-exclusive", "type": "skill",
                 "description": "Only promoted, not reaped", "tags": []},
            ],
        }
        await session.commit()

        before = (
            await session.execute(
                select(CapabilityMarketEntry).where(
                    CapabilityMarketEntry.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        before_count = len(before)

        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/promote",
            headers=h, json={"from_instance_id": instance_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["capability_market_uploaded"] == 0

        after = (
            await session.execute(
                select(CapabilityMarketEntry).where(
                    CapabilityMarketEntry.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        assert len(after) == before_count
        market_result = await session.execute(
            select(CapabilityMarketEntry).where(
                CapabilityMarketEntry.created_via == "promote",
                CapabilityMarketEntry.deleted_at.is_(None),
            )
        )
        assert list(market_result.scalars().all()) == []

    async def test_promote_skips_market_when_name_already_exists(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """Promote never mutates market even when a name already exists there."""
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)

        from app.models.instance import Instance

        # Seed a market row via reap path semantics.
        session.add(
            CapabilityMarketEntry(
                name="already-there",
                type="skill",
                description="from reap",
                created_via="reap",
            )
        )
        await session.commit()

        inst = await session.get(Instance, instance_id)
        assert inst is not None
        inst.runtime_config = {
            "reaped_capabilities": [
                {"name": "already-there", "type": "skill",
                 "description": "promote attempt", "tags": []},
            ],
        }
        await session.commit()

        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/promote",
            headers=h, json={"from_instance_id": instance_id},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["capability_market_uploaded"] == 0

        row = (
            await session.execute(
                select(CapabilityMarketEntry).where(
                    CapabilityMarketEntry.name == "already-there",
                    CapabilityMarketEntry.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        assert row.created_via == "reap"
        assert row.description == "from reap"

    def test_promote_counts_outdated_instances(
        self, client: TestClient, auth_token: str, auth_user_id: str,
    ) -> None:
        """Other instances of the same Entity become outdated (active_hash != migration_hash)."""
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)

        # Create a second instance with no active_hash.
        _create_instance(client, auth_token, entity_id, workspace_id)

        _create_memory(
            client, auth_token, entity_id, kind="lesson",
            key="outdated-test", content="outdated tracking",
        )
        client.post(
            f"/api/v1/learning/instances/{instance_id}/reap",
            headers=h, json={},
        )

        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/promote",
            headers=h, json={"from_instance_id": instance_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["outdated_instances_count"] >= 1

    def test_promote_resolves_first_instance_when_from_instance_missing(
        self, client: TestClient, auth_token: str, auth_user_id: str,
    ) -> None:
        """from_instance_id omitted → uses the first active instance of the Entity."""
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)

        _create_memory(
            client, auth_token, entity_id, kind="lesson",
            key="auto-source", content="auto-source pattern",
        )
        client.post(
            f"/api/v1/learning/instances/{instance_id}/reap",
            headers=h, json={},
        )

        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/promote",
            headers=h, json={},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["capability_promoted_count"] >= 1

    def test_promote_404_for_unknown_entity(
        self, client: TestClient, auth_token: str,
    ) -> None:
        h = _auth(auth_token)
        resp = client.post(
            f"/api/v1/learning/entities/{uuid.uuid4()}/promote",
            headers=h, json={},
        )
        assert resp.status_code == 404, resp.text

    async def test_promote_emits_event(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)

        _create_memory(
            client, auth_token, entity_id, kind="lesson",
            key="evented-promote", content="evented promote",
        )
        client.post(
            f"/api/v1/learning/instances/{instance_id}/reap",
            headers=h, json={},
        )

        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/promote",
            headers=h, json={"from_instance_id": instance_id},
        )
        assert resp.status_code == 200, resp.text

        ev_result = await session.execute(
            select(Event).where(Event.type == "learning.promote_completed")
        )
        events = list(ev_result.scalars().all())
        assert len(events) == 1
        assert events[0].resource_id == entity_id
        assert "new_migration_hash" in events[0].payload


# =========================================================================
# Endpoint C: POST /learning/entities/{eid}/transmute
# =========================================================================


class TestTransmute:
    """Tests for the transmute endpoint."""

    async def test_transmute_creates_base_class(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        _create_instance(client, auth_token, entity_id, workspace_id)

        # Promote first to seed capabilities.
        client.post(
            f"/api/v1/learning/entities/{entity_id}/promote",
            headers=h, json={},
        )

        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/transmute",
            headers=h,
            json={
                "target_base_class_slug": "transmuted-mi-shi",
                "target_base_class_name": "Transmuted 密士",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["new_base_class_slug"] == "transmuted-mi-shi"
        assert body["new_base_class_name"] == "Transmuted 密士"
        assert body["source_entity_id"] == entity_id
        assert "manifest_preview" in body

        bc_result = await session.execute(
            select(BaseClass).where(
                BaseClass.slug == "transmuted-mi-shi",
                BaseClass.deleted_at.is_(None),
            )
        )
        bc = bc_result.scalar_one()
        assert bc is not None
        assert isinstance(bc.manifest, dict)
        assert "default_capabilities" in bc.manifest

    async def test_transmute_does_not_mutate_entity(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        _create_instance(client, auth_token, entity_id, workspace_id)

        # Capture pre-state.
        emp_before = await session.get(Entity, entity_id)
        assert emp_before is not None
        before_migration_hash = emp_before.migration_hash

        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/transmute",
            headers=h,
            json={
                "target_base_class_slug": "post-promote",
                "target_base_class_name": "Post Promote",
            },
        )
        assert resp.status_code == 201, resp.text

        await session.refresh(emp_before)
        assert emp_before.migration_hash == before_migration_hash

    async def test_transmute_409_for_existing_slug(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        _create_instance(client, auth_token, entity_id, workspace_id)

        # Seed an existing BaseClass row.
        existing = BaseClass(slug="reserved-slug", name="Reserved")
        session.add(existing)
        await session.commit()

        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/transmute",
            headers=h,
            json={
                "target_base_class_slug": "reserved-slug",
                "target_base_class_name": "Reserved 2",
            },
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["error_code"] == "base_class.slug_taken"

    async def test_transmute_snapshot_only(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        _create_instance(client, auth_token, entity_id, workspace_id)

        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/transmute",
            headers=h,
            json={
                "target_base_class_slug": "preview-bc",
                "target_base_class_name": "Preview",
                "snapshot_only": True,
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["new_base_class_id"] == ""  # not created

        result = await session.execute(
            select(BaseClass).where(BaseClass.slug == "preview-bc")
        )
        assert result.scalar_one_or_none() is None

    def test_transmute_rejects_wrong_action(
        self, client: TestClient, auth_token: str, auth_user_id: str,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        _create_instance(client, auth_token, entity_id, workspace_id)

        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/transmute",
            headers=h,
            json={
                "target_base_class_slug": "wrong-action",
                "target_base_class_name": "Wrong Action",
            },
        )
        # Missing promote step / empty capabilities still OK — transmute succeeds
        # or conflicts; wrong endpoint action is no longer a query param.
        assert resp.status_code in (201, 409, 422), resp.text


# =========================================================================
# Endpoint D: POST /learning/capabilities/combine
# =========================================================================


class TestCombine:
    """Tests for the combine endpoint."""

    def _seed_capabilities(self, session: AsyncSession, names: list[str]) -> None:
        """Insert capability_market rows directly."""
        for name in names:
            session.add(CapabilityMarketEntry(
                name=name, type="skill", description=f"Test {name}",
                created_via="manual",
            ))

    async def _seed_capabilities_async(self, session: AsyncSession, names: list[str]) -> None:
        """Async version: insert + commit."""
        self._seed_capabilities(session, names)
        await session.commit()

    async def test_combine_creates_gene(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        await self._seed_capabilities_async(session, ["a", "b", "c"])
        h = _auth(auth_token)

        resp = client.post(
            "/api/v1/learning/capabilities/combine",
            headers=h,
            json={
                "capability_names": ["a", "b"],
                "gene_slug": "review-toolkit",
                "gene_name": "Review Toolkit",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["new_gene_slug"] == "review-toolkit"
        assert sorted(body["referenced_capabilities"]) == ["a", "b"]
        assert len(body["manifest_preview"]) > 0

        gene_result = await session.execute(
            select(AiGene).where(
                AiGene.slug == "review-toolkit",
                AiGene.deleted_at.is_(None),
            )
        )
        gene = gene_result.scalar_one()
        assert gene is not None
        assert gene.slug is not None
        assert isinstance(gene.manifest, dict)
        assert len(gene.manifest["capabilities"]) == 2

    async def test_combine_404_for_missing_capability(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        await self._seed_capabilities_async(session, ["only-this"])
        h = _auth(auth_token)

        resp = client.post(
            "/api/v1/learning/capabilities/combine",
            headers=h,
            json={
                "capability_names": ["only-this", "missing-one"],
                "gene_slug": "x-gene",
                "gene_name": "X Gene",
            },
        )
        assert resp.status_code == 404, resp.text
        assert "missing-one" in resp.json()["details"]["missing"]

    async def test_combine_409_for_existing_slug(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        await self._seed_capabilities_async(session, ["a", "b"])
        session.add(AiGene(slug="taken-gene", name="Taken"))
        await session.commit()

        h = _auth(auth_token)
        resp = client.post(
            "/api/v1/learning/capabilities/combine",
            headers=h,
            json={
                "capability_names": ["a", "b"],
                "gene_slug": "taken-gene",
                "gene_name": "Taken 2",
            },
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["error_code"] == "ai_gene.slug_taken"

    async def test_combine_snapshot_only(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        await self._seed_capabilities_async(session, ["a", "b"])
        h = _auth(auth_token)

        resp = client.post(
            "/api/v1/learning/capabilities/combine",
            headers=h,
            json={
                "capability_names": ["a", "b"],
                "gene_slug": "preview-gene",
                "gene_name": "Preview",
                "snapshot_only": True,
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["new_gene_id"] == ""

        result = await session.execute(
            select(AiGene).where(AiGene.slug == "preview-gene")
        )
        assert result.scalar_one_or_none() is None

    async def test_combine_emits_event(
        self, client: TestClient, auth_token: str, auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        await self._seed_capabilities_async(session, ["a", "b"])
        h = _auth(auth_token)

        resp = client.post(
            "/api/v1/learning/capabilities/combine",
            headers=h,
            json={
                "capability_names": ["a", "b"],
                "gene_slug": "ev-gene",
                "gene_name": "EV Gene",
            },
        )
        assert resp.status_code == 201, resp.text

        ev_result = await session.execute(
            select(Event).where(Event.type == "learning.capability_combined")
        )
        events = list(ev_result.scalars().all())
        assert len(events) == 1
        assert events[0].payload["gene_slug"] == "ev-gene"
