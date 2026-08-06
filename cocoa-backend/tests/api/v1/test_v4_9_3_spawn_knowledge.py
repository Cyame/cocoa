"""v4.9.3 spawn-time knowledge injection + self-consistency check.

Worker C slice — the INSTANCE SPAWN layer. Covers:

- (a) spawn injects ``runtime_config["knowledge"] = {"env": {slug: body},
  "files": []}`` from the has-knowledge union (BaseClass ∪ Entity), each slug
  resolved through the knowledge_entries scope-chain rules.
- (b) self-consistency pass: has ⊇ required → no warning, no audit event.
- (c) self-consistency fail: missing required → response warning
  (``knowledge_consistency_warning: {missing: [...]}``) + audit event, but
  the spawn still succeeds (non-blocking).
- (d) deploy env splice: ``_instance_pod_env_async`` maps
  ``runtime_config["knowledge"]["env"]`` onto ``KNOWLEDGE_<SLUG>`` pod vars.

Baseline pin: an instance spawned from an entity with no has-knowledge keeps
``runtime_config.agent_config`` and gets NO ``knowledge`` key — that behavior
passed on the unchanged code and is still pinned here.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.core.capabilities import attach_entity_capability, upsert_capability
from app.models.base_class import BaseClass
from app.models.entity import Entity
from app.models.event import Event
from app.models.knowledge import KnowledgeEntry
from app.models.organization import Namespace
from app.models.workspace import Workspace
from app.services.deploy_service import _instance_pod_env_async

_ATOMS = (
    "can_manage_namespace",
    "can_edit_workspace",
    "can_operate_workspace",
    "can_view_workspace",
    "can_manage_capabilities",
)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, prefix: str) -> tuple[str, str]:
    username = f"{prefix}-{uuid.uuid4().hex[:6]}"
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@t.co", "password": "password123"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["id"]


async def _org_bundle(session: AsyncSession, user_id: str) -> str:
    """Default-org bundle with workspace atoms granted; returns org id."""
    from app.core.gene_atoms import ensure_atom_genes
    from app.core.org_contract import ensure_org_contract, grant_atoms
    from app.models.organization import Organization

    await ensure_atom_genes(session)
    org = (
        await session.execute(
            select(Organization).where(
                Organization.slug == "default",
                Organization.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if org is None:
        org = Organization(slug="default", name="Default World")
        session.add(org)
        await session.flush()
    contract = await ensure_org_contract(session, organization_id=org.id, user_id=user_id)
    await grant_atoms(session, contract.id, _ATOMS)
    await session.commit()
    return org.id


async def _spawn_stack(
    client: TestClient,
    session: AsyncSession,
    *,
    token: str,
    user_id: str,
    entity_has: list[str] | None = None,
    base_class_has: list[str] | None = None,
) -> tuple[str, str, str]:
    """Org bundle + Namespace/Workspace + (optional) BaseClass + Entity.

    Returns ``(entity_id, workspace_id, org_id)``. Entity / BaseClass rows
    are created via the session (the spawn layer reads BaseClass by slug —
    no preset-registry gate).
    """
    org_id = await _org_bundle(session, user_id)
    ns = Namespace(org_id=org_id, slug=f"v493ns-{uuid.uuid4().hex[:6]}", name="NS")
    session.add(ns)
    await session.flush()
    ws = Workspace(namespace_id=ns.id, name="WS", slug=f"v493ws-{uuid.uuid4().hex[:8]}")
    session.add(ws)
    await session.flush()

    preset_slug: str | None = None
    if base_class_has is not None:
        bc = BaseClass(
            slug=f"v493bc-{uuid.uuid4().hex[:8]}",
            name="V493 BC",
            scope="org",
            organization_id=org_id,
            has_knowledge=base_class_has,
        )
        session.add(bc)
        await session.flush()
        preset_slug = bc.slug

    entity = Entity(
        namespace_id=ns.id,
        name="V493 Entity",
        slug=f"v493ent-{uuid.uuid4().hex[:8]}",
        rank="intern",
        preset_slug=preset_slug,
        has_knowledge=entity_has,
    )
    session.add(entity)
    await session.commit()
    return entity.id, ws.id, org_id


def _spawn(
    client: TestClient,
    token: str,
    *,
    entity_id: str,
    workspace_id: str,
    org_id: str,
):
    return client.post(
        "/api/v1/instances",
        headers={**_auth(token), "X-Organization-Id": org_id},
        json={"entity_id": entity_id, "workspace_id": workspace_id},
    )


async def _insert_entry(
    session: AsyncSession,
    *,
    key: str,
    body: str,
    title: str = "Entry",
) -> None:
    session.add(KnowledgeEntry(key=key, title=title, body=body, scope="system"))
    await session.flush()


async def _events_for(
    session: AsyncSession, event_type: str, instance_id: str
) -> list[Event]:
    result = await session.execute(
        select(Event).where(
            Event.type == event_type,
            Event.resource_id == instance_id,
        )
    )
    return list(result.scalars().all())


class TestSpawnBaseline:
    """Baseline pin — must pass on unchanged code."""

    @pytest.mark.asyncio
    async def test_spawn_without_has_knowledge_keeps_agent_config_no_knowledge_key(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        token, user_id = _register(client, "v493base")
        entity_id, workspace_id, org_id = await _spawn_stack(
            client, session, token=token, user_id=user_id
        )

        resp = _spawn(
            client, token, entity_id=entity_id, workspace_id=workspace_id, org_id=org_id
        )
        assert resp.status_code == 201, resp.text
        rc = resp.json()["runtime_config"]
        assert isinstance(rc, dict)
        assert "agent_config" in rc
        assert "knowledge" not in rc


class TestSpawnKnowledgeInjection:
    @pytest.mark.asyncio
    async def test_spawn_injects_knowledge_env_from_entity_has(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        token, user_id = _register(client, "v493inj")
        entity_id, workspace_id, org_id = await _spawn_stack(
            client,
            session,
            token=token,
            user_id=user_id,
            entity_has=["docs-runbook"],
        )
        await _insert_entry(
            session,
            key="docs-runbook",
            body="The incident runbook lives in /workspace/docs.",
        )
        await session.commit()

        resp = _spawn(
            client, token, entity_id=entity_id, workspace_id=workspace_id, org_id=org_id
        )
        assert resp.status_code == 201, resp.text
        rc = resp.json()["runtime_config"]
        assert rc["knowledge"] == {
            "env": {"docs-runbook": "The incident runbook lives in /workspace/docs."},
            "files": [],
        }
        assert "agent_config" in rc

    @pytest.mark.asyncio
    async def test_spawn_unions_base_class_and_entity_has_knowledge(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        token, user_id = _register(client, "v493uni")
        entity_id, workspace_id, org_id = await _spawn_stack(
            client,
            session,
            token=token,
            user_id=user_id,
            entity_has=["docs-runbook"],
            base_class_has=["docs-collab"],
        )
        await _insert_entry(session, key="docs-runbook", body="runbook body")
        await _insert_entry(session, key="docs-collab", body="collab body")
        await session.commit()

        resp = _spawn(
            client, token, entity_id=entity_id, workspace_id=workspace_id, org_id=org_id
        )
        assert resp.status_code == 201, resp.text
        env = resp.json()["runtime_config"]["knowledge"]["env"]
        assert env == {"docs-collab": "collab body", "docs-runbook": "runbook body"}


class TestSelfConsistencyCheck:
    async def _attach_required(
        self,
        session: AsyncSession,
        *,
        entity_id: str,
        required: list[str],
    ) -> None:
        cap = await upsert_capability(
            session,
            name=f"v493cap-{uuid.uuid4().hex[:8]}",
            required_knowledge=required,
        )
        await attach_entity_capability(session, entity_id=entity_id, capability_id=cap.id)
        await session.commit()

    @pytest.mark.asyncio
    async def test_consistency_pass_has_covers_required_no_warning(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        token, user_id = _register(client, "v493pass")
        entity_id, workspace_id, org_id = await _spawn_stack(
            client,
            session,
            token=token,
            user_id=user_id,
            entity_has=["docs-runbook"],
        )
        await _insert_entry(session, key="docs-runbook", body="runbook body")
        await self._attach_required(
            session, entity_id=entity_id, required=["docs-runbook"]
        )

        resp = _spawn(
            client, token, entity_id=entity_id, workspace_id=workspace_id, org_id=org_id
        )
        assert resp.status_code == 201, resp.text
        assert resp.json().get("knowledge_consistency_warning") is None
        instance_id = resp.json()["id"]
        assert await _events_for(
            session, "instance.knowledge_inconsistent", instance_id
        ) == []

    @pytest.mark.asyncio
    async def test_consistency_missing_warns_but_spawn_succeeds(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        token, user_id = _register(client, "v493miss")
        entity_id, workspace_id, org_id = await _spawn_stack(
            client,
            session,
            token=token,
            user_id=user_id,
            entity_has=["docs-runbook"],
        )
        await _insert_entry(session, key="docs-runbook", body="runbook body")
        await self._attach_required(
            session,
            entity_id=entity_id,
            required=["docs-runbook", "docs-missing"],
        )

        resp = _spawn(
            client, token, entity_id=entity_id, workspace_id=workspace_id, org_id=org_id
        )
        assert resp.status_code == 201, resp.text  # non-blocking
        assert resp.json()["knowledge_consistency_warning"] == {
            "missing": ["docs-missing"]
        }
        instance_id = resp.json()["id"]
        events = await _events_for(
            session, "instance.knowledge_inconsistent", instance_id
        )
        assert len(events) == 1
        assert events[0].payload["missing"] == ["docs-missing"]
        assert events[0].payload["entity_id"] == entity_id


class TestDeployEnvSplice:
    @pytest.mark.asyncio
    async def test_pod_env_includes_knowledge_vars(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        token, user_id = _register(client, "v493dep")
        entity_id, workspace_id, org_id = await _spawn_stack(
            client,
            session,
            token=token,
            user_id=user_id,
            entity_has=["docs-runbook"],
        )
        await _insert_entry(session, key="docs-runbook", body="runbook body")
        await session.commit()

        resp = _spawn(
            client, token, entity_id=entity_id, workspace_id=workspace_id, org_id=org_id
        )
        assert resp.status_code == 201, resp.text
        instance_id = resp.json()["id"]

        env = await _instance_pod_env_async(session, instance_id, "proxy-tok")
        assert env["KNOWLEDGE_DOCS_RUNBOOK"] == "runbook body"

    @pytest.mark.asyncio
    async def test_pod_env_without_knowledge_has_no_knowledge_vars(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        token, user_id = _register(client, "v493dep2")
        entity_id, workspace_id, org_id = await _spawn_stack(
            client, session, token=token, user_id=user_id
        )
        resp = _spawn(
            client, token, entity_id=entity_id, workspace_id=workspace_id, org_id=org_id
        )
        assert resp.status_code == 201, resp.text
        instance_id = resp.json()["id"]

        env = await _instance_pod_env_async(session, instance_id, "proxy-tok")
        assert not any(k.startswith("KNOWLEDGE_") for k in env)
