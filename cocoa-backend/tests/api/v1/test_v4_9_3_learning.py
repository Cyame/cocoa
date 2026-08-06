"""v4.9.3 learning semantics — distill/promote/transmute + knowledge dual dimension.

Worker BD slice (LEARNING SEMANTICS):

- distill = Entity memory → **capability_market** entries (created_via=distill,
  org scope, required_knowledge declared, no has_knowledge).
- engine=llm with no configured provider → degrades to heuristic with
  ``engine_used="heuristic"`` + ``llm_unavailable_degraded_to_heuristic``
  warning (never 422/500).
- promote = Instance → Entity: aggregates the source instance's
  ``runtime_config["knowledge"]["env"]`` keys into ``entity.has_knowledge``.
- transmute = Entity → BaseClass: ``default_gene_refs`` derived from the
  entity's attached genes (written into ``base_class_ai_genes`` junction)
  + ``has_knowledge`` mounted from the entity.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models.ai_gene import AiGene, BaseClassAiGene
from app.models.base_class import BaseClass
from app.models.capability_market import CapabilityMarketEntry
from app.models.entity import Entity
from app.models.instance import Instance
from app.models.junctions import EntityAiGene
from app.models.user import User


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


@pytest.fixture
def auth_token(client: TestClient) -> str:
    client.post("/api/v1/auth/register", json={
        "username": "v493_learning",
        "email": "v493_learning@test.com",
        "password": "password123",
    })
    resp = client.post("/api/v1/auth/login", json={
        "username": "v493_learning",
        "password": "password123",
    })
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def auth_user_id(auth_token: str, session: AsyncSession) -> str:
    result = await session.execute(
        select(User).where(User.username == "v493_learning"),
    )
    user: User = result.scalars().first()
    return user.id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup_workspace(client: TestClient, token: str) -> str:
    slug = f"v493-ws-{uuid.uuid4().hex[:6]}"
    resp = client.post("/api/v1/workspaces", headers=_auth(token), json={
        "name": f"V493 Workspace {slug}",
        "slug": slug,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_entity(client: TestClient, token: str) -> str:
    slug = f"v493-emp-{uuid.uuid4().hex[:6]}"
    resp = client.post("/api/v1/entities", headers=_auth(token), json={
        "name": "V493 Entity", "slug": slug,
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
# (a) distill = Entity memory → capability_market (created_via=distill)
# =========================================================================


class TestDistillToCapabilityMarket:
    async def test_distill_creates_market_entry_with_required_knowledge(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """distill writes capability_market rows (created_via=distill) with
        required_knowledge slugs and does NOT create a BaseClass."""
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        _create_instance(client, auth_token, entity_id, workspace_id)

        _create_memory(
            client, auth_token, entity_id, kind="lesson",
            key="debug-memory-leak",
            content="A" * 80 + " circular references cause memory leaks.",
        )
        _create_memory(
            client, auth_token, entity_id, kind="decision",
            key="deploy-rollback", content="Rollback strategy decided.",
        )

        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/distill",
            headers=h,
            json={"target_skill_slug": "my-skill"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()

        # Response exposes created capabilities + gene_suggestion + engine_used.
        names = {c["name"] for c in body["capability_candidates"]}
        assert "debug-memory-leak" in names
        assert "deploy-rollback" in names
        assert body["engine_used"] == "heuristic"
        assert body["warnings"] == []
        assert body["gene_suggestion"]

        # No BaseClass is created anymore (memory → market, not manifest).
        bc_result = await session.execute(
            select(BaseClass).where(
                BaseClass.slug == "base-skill-my-skill",
                BaseClass.deleted_at.is_(None),
            )
        )
        assert bc_result.scalar_one_or_none() is None

        # Market rows exist with created_via=distill + required_knowledge.
        market_result = await session.execute(
            select(CapabilityMarketEntry).where(
                CapabilityMarketEntry.name.in_(["debug-memory-leak", "deploy-rollback"]),
                CapabilityMarketEntry.deleted_at.is_(None),
            )
        )
        rows = {r.name: r for r in market_result.scalars().all()}
        assert set(rows) == {"debug-memory-leak", "deploy-rollback"}
        assert rows["debug-memory-leak"].created_via == "distill"
        # required knowledge = key-prefix slug (debug / deploy).
        assert rows["debug-memory-leak"].required_knowledge == ["debug"]
        assert rows["deploy-rollback"].required_knowledge == ["deploy"]

    async def test_distill_idempotent_on_second_call(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """Re-distilling the same skill upserts idempotently — no 409."""
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        _create_instance(client, auth_token, entity_id, workspace_id)
        _create_memory(
            client, auth_token, entity_id, kind="lesson",
            key="alpha-pattern", content="A" * 60,
        )

        resp1 = client.post(
            f"/api/v1/learning/entities/{entity_id}/distill",
            headers=h, json={"target_skill_slug": "my-skill"},
        )
        assert resp1.status_code == 201, resp1.text
        resp2 = client.post(
            f"/api/v1/learning/entities/{entity_id}/distill",
            headers=h, json={"target_skill_slug": "my-skill"},
        )
        assert resp2.status_code == 201, resp2.text
        assert resp2.json()["capability_market_created"] == 0

    def test_distill_no_memory_still_422(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """No memory entries → 422 learning.no_memory (contract kept)."""
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        _create_instance(client, auth_token, entity_id, workspace_id)

        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/distill",
            headers=h, json={"target_skill_slug": "foo-bar"},
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["error_code"] == "learning.no_memory"


# =========================================================================
# (b) engine=llm without provider → degrade to heuristic (Q5)
# =========================================================================


class TestDistillEngineSelection:
    async def test_engine_llm_no_provider_degrades_to_heuristic(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """engine=llm with no org provider → heuristic + warning, not 422/500."""
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        _create_instance(client, auth_token, entity_id, workspace_id)
        _create_memory(
            client, auth_token, entity_id, kind="lesson",
            key="debug-concurrency",
            content="A" * 60 + " concurrency debugging lesson",
        )

        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/distill",
            headers=h,
            json={"target_skill_slug": "llm-skill", "engine": "llm"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["engine_used"] == "heuristic"
        assert "llm_unavailable_degraded_to_heuristic" in body["warnings"]
        # The heuristic still produced candidates.
        assert any(c["name"] == "debug-concurrency" for c in body["capability_candidates"])

    async def test_engine_heuristic_default(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """engine omitted → heuristic, no warnings."""
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        _create_instance(client, auth_token, entity_id, workspace_id)
        _create_memory(
            client, auth_token, entity_id, kind="lesson",
            key="default-engine", content="A" * 60,
        )

        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/distill",
            headers=h, json={"target_skill_slug": "dflt-skill"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["engine_used"] == "heuristic"
        assert body["warnings"] == []


# =========================================================================
# (c) promote = Instance → Entity: has_knowledge aggregate
# =========================================================================


class TestPromoteHasKnowledge:
    async def test_promote_aggregates_instance_knowledge_env_keys(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """promote unions instance runtime_config knowledge env keys into
        entity.has_knowledge, atomically with the capability writes."""
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)

        entity = await session.get(Entity, entity_id)
        assert entity is not None
        entity.has_knowledge = ["k0"]
        inst = await session.get(Instance, instance_id)
        assert inst is not None
        inst.runtime_config = {
            "reaped_capabilities": [
                {"name": "promoted-cap", "type": "skill",
                 "description": "x", "tags": []},
            ],
            "knowledge": {"env": {"k1": "v1", "k2": "v2"}},
        }
        await session.commit()

        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/promote",
            headers=h, json={"from_instance_id": instance_id},
        )
        assert resp.status_code == 200, resp.text
        assert sorted(resp.json()["has_knowledge"]) == ["k0", "k1", "k2"]

        await session.refresh(entity)
        assert sorted(entity.has_knowledge or []) == ["k0", "k1", "k2"]

    async def test_promote_fork_inherits_has_knowledge(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """fork mode copies source has_knowledge + instance env keys."""
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        instance_id = _create_instance(client, auth_token, entity_id, workspace_id)

        entity = await session.get(Entity, entity_id)
        assert entity is not None
        entity.has_knowledge = ["src-knowledge"]
        inst = await session.get(Instance, instance_id)
        assert inst is not None
        inst.runtime_config = {"knowledge": {"env": {"fork-knowledge": "v"}}}
        await session.commit()

        new_slug = f"v493-fork-{uuid.uuid4().hex[:6]}"
        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/promote",
            headers=h,
            json={
                "mode": "fork",
                "from_instance_id": instance_id,
                "new_entity_name": "Forked Entity",
                "new_entity_slug": new_slug,
            },
        )
        assert resp.status_code == 200, resp.text
        new_entity = (
            await session.execute(
                select(Entity).where(
                    Entity.slug == new_slug, Entity.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        assert new_entity is not None
        assert sorted(new_entity.has_knowledge or []) == [
            "fork-knowledge", "src-knowledge",
        ]


# =========================================================================
# (d) transmute = Entity → BaseClass: genes + has_knowledge
# =========================================================================


class TestTransmuteGenesAndKnowledge:
    async def test_transmute_writes_gene_junction_and_mounts_has_knowledge(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """transmute derives default_gene_refs from the entity's genes, writes
        the base_class_ai_genes junction, and mounts has_knowledge."""
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        _create_instance(client, auth_token, entity_id, workspace_id)

        entity = await session.get(Entity, entity_id)
        assert entity is not None
        entity.has_knowledge = ["entity-docs", "entity-runbook"]
        gene = AiGene(
            slug=f"v493-gene-{uuid.uuid4().hex[:6]}",
            name="V493 Gene",
            manifest={"capabilities": []},
        )
        session.add(gene)
        await session.flush()
        session.add(EntityAiGene(entity_id=entity_id, ai_gene_id=gene.id))
        await session.commit()

        bc_slug = f"v493-bc-{uuid.uuid4().hex[:6]}"
        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/transmute",
            headers=h,
            json={
                "target_base_class_slug": bc_slug,
                "target_base_class_name": "V493 Transmuted",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert sorted(body["default_gene_refs"]) == [gene.slug]
        assert sorted(body["has_knowledge"]) == ["entity-docs", "entity-runbook"]
        assert body["manifest_preview"]["default_gene_refs"] == [gene.slug]
        assert sorted(body["manifest_preview"]["has_knowledge"]) == [
            "entity-docs", "entity-runbook",
        ]

        bc = (
            await session.execute(
                select(BaseClass).where(
                    BaseClass.slug == bc_slug, BaseClass.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        assert sorted(bc.has_knowledge or []) == ["entity-docs", "entity-runbook"]

        junction = (
            await session.execute(
                select(BaseClassAiGene).where(
                    BaseClassAiGene.base_class_id == bc.id,
                    BaseClassAiGene.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        assert [j.ai_gene_id for j in junction] == [gene.id]

    async def test_transmute_snapshot_preview_shows_real_genes(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """snapshot_only preview shows the real default_gene_refs / has_knowledge."""
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token)
        entity_id = _create_entity(client, auth_token)
        _create_instance(client, auth_token, entity_id, workspace_id)

        entity = await session.get(Entity, entity_id)
        assert entity is not None
        entity.has_knowledge = ["snap-docs"]
        gene = AiGene(
            slug=f"v493-snap-gene-{uuid.uuid4().hex[:6]}",
            name="Snap Gene",
            manifest={},
        )
        session.add(gene)
        await session.flush()
        session.add(EntityAiGene(entity_id=entity_id, ai_gene_id=gene.id))
        await session.commit()

        resp = client.post(
            f"/api/v1/learning/entities/{entity_id}/transmute",
            headers=h,
            json={
                "target_base_class_slug": f"v493-snap-bc-{uuid.uuid4().hex[:6]}",
                "target_base_class_name": "Snap",
                "snapshot_only": True,
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["manifest_preview"]["default_gene_refs"] == [gene.slug]
        assert body["manifest_preview"]["has_knowledge"] == ["snap-docs"]
