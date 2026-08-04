"""v4.4 Clone Operations tests.

Covers:
- BaseClass / Entity / Organization / Workspace clone deep-copy semantics.
- New UUIDs; no FK back to source junctions.
- Missing gene -> 403.
- Org clone: only caller has OrgContract; zero copied OrganizationContract;
  zero NamespaceContract on new NS; other source members cannot see new org.
- WS clone: awakened induced subgraph isomorphic; counterexample A(awakened)
  -> B(lost) -> C(awakened) does NOT create A-C; dropped passage events.
- Instance clone rejected (404).
- No Instance rows created by any clone.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from app.models.ai_gene import BaseClassAiGene
from app.models.central_hub import CentralHub, Vault
from app.models.entity import Entity
from app.models.instance import Instance
from app.models.junctions import BaseClassCapability, EntityAiGene, EntityCapability
from app.models.namespace_contract import NamespaceContract
from app.models.organization import Namespace, Organization
from app.models.organization_contract import OrganizationContract
from app.models.workspace import Membership, Passage, Workspace


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, username: str, email: str) -> tuple[str, str]:
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": "password123"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["id"]


def _uid() -> str:
    return uuid.uuid4().hex[:6]


def _create_org(client: TestClient, token: str, slug: str, name: str) -> dict:
    resp = client.post(
        "/api/v1/organizations", headers=_auth(token), json={"slug": slug, "name": name}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW", 100_000)


async def _verify_session(db_url: str):
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


# ---------------------------------------------------------------------------
# BaseClass clone
# ---------------------------------------------------------------------------


class TestCloneBaseClass:
    @pytest.mark.asyncio
    async def test_clone_creates_new_uuid_and_junctions(
        self, client: TestClient, session: AsyncSession, create_org_bundle, db_url: str
    ) -> None:
        from app.models.ai_gene import AiGene
        from app.models.capability_market import CapabilityMarketEntry

        _register(client, f"bc-sa-{_uid()}", f"bc-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"bc-m-{_uid()}", f"bc-m-{_uid()}@t.co")
        bundle = await create_org_bundle(
            member_id,
            atoms=("can_clone_base_class", "can_manage_organization",
                   "can_manage_ai_genes", "can_manage_capabilities"),
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        bc = client.post(
            "/api/v1/base-classes", headers=headers,
            json={"slug": f"bc-{_uid()}", "name": "Source BC", "scope": "org"},
        )
        assert bc.status_code == 201, bc.text
        bc_id = bc.json()["id"]

        gene = AiGene(slug=f"gene-{_uid()}", name="G", scope="org", organization_id=bundle.org.id)
        session.add(gene)
        await session.flush()
        cap = CapabilityMarketEntry(
            name=f"cap-{_uid()}", type="skill", scope="org",
            organization_id=bundle.org.id, created_via="manual",
        )
        session.add(cap)
        await session.commit()

        r1 = client.post(f"/api/v1/base-classes/{bc_id}/ai-genes", headers=headers,
                         json={"ai_gene_id": gene.id})
        assert r1.status_code == 201, r1.text
        r2 = client.post(f"/api/v1/base-classes/{bc_id}/capabilities", headers=headers,
                         json={"capability_id": cap.id})
        assert r2.status_code == 201, r2.text

        resp = client.post(f"/api/v1/base-classes/{bc_id}/clone", headers=headers, json={})
        assert resp.status_code == 201, resp.text
        new_id = resp.json()["id"]
        assert new_id != bc_id
        assert resp.json()["slug"] != bc.json()["slug"]

        engine, factory = await _verify_session(db_url)
        try:
            async with factory() as verify:
                new_gene_links = (await verify.execute(select(BaseClassAiGene).where(
                    BaseClassAiGene.base_class_id == new_id,
                    BaseClassAiGene.deleted_at.is_(None)
                ))).scalars().all()
                assert len(new_gene_links) == 1

                new_cap_links = (await verify.execute(select(BaseClassCapability).where(
                    BaseClassCapability.base_class_id == new_id,
                    BaseClassCapability.deleted_at.is_(None)
                ))).scalars().all()
                assert len(new_cap_links) == 1

                source_gene_links = (await verify.execute(select(BaseClassAiGene).where(
                    BaseClassAiGene.base_class_id == bc_id,
                    BaseClassAiGene.deleted_at.is_(None)
                ))).scalars().all()
                assert new_gene_links[0].id != source_gene_links[0].id

                from app.models.event import Event

                events = (await verify.execute(select(Event).where(
                    Event.type == "base_class.cloned"
                ))).scalars().all()
                assert len(events) == 1
                assert events[0].payload["source_id"] == bc_id
                assert events[0].payload["new_id"] == new_id
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_clone_without_permission_403(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(client, f"bc-np-sa-{_uid()}", f"bc-np-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"bc-np-m-{_uid()}", f"bc-np-m-{_uid()}@t.co")
        bundle = await create_org_bundle(member_id, atoms=("can_manage_organization",))
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        bc = client.post(
            "/api/v1/base-classes", headers=headers,
            json={"slug": f"bcnp-{_uid()}", "name": "BC", "scope": "org"},
        )
        assert bc.status_code == 201, bc.text

        resp = client.post(f"/api/v1/base-classes/{bc.json()['id']}/clone", headers=headers, json={})
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

    @pytest.mark.asyncio
    async def test_clone_with_custom_name_and_slug(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(client, f"bc-cn-sa-{_uid()}", f"bc-cn-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"bc-cn-m-{_uid()}", f"bc-cn-m-{_uid()}@t.co")
        bundle = await create_org_bundle(
            member_id, atoms=("can_clone_base_class", "can_manage_organization")
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        bc = client.post(
            "/api/v1/base-classes", headers=headers,
            json={"slug": f"bccn-{_uid()}", "name": "Source", "scope": "org"},
        )
        assert bc.status_code == 201, bc.text

        resp = client.post(
            f"/api/v1/base-classes/{bc.json()['id']}/clone", headers=headers,
            json={"name": "Custom Name", "slug": f"custom-slug-{_uid()}"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["name"] == "Custom Name"
        assert resp.json()["slug"].startswith("custom-slug-")


# ---------------------------------------------------------------------------
# Entity clone
# ---------------------------------------------------------------------------


class TestCloneEntity:
    @pytest.mark.asyncio
    async def test_clone_creates_new_uuid_and_junctions(
        self, client: TestClient, session: AsyncSession, create_org_bundle,
        namespace_factory, db_url: str
    ) -> None:
        from app.models.ai_gene import AiGene
        from app.models.capability_market import CapabilityMarketEntry

        _register(client, f"en-sa-{_uid()}", f"en-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"en-m-{_uid()}", f"en-m-{_uid()}@t.co")
        ns = await namespace_factory()
        bundle = await create_org_bundle(
            member_id,
            atoms=("can_clone_entity", "can_manage_namespace"),
            namespace=ns,
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        gene = AiGene(slug=f"gene-{_uid()}", name="G", scope="org", organization_id=bundle.org.id)
        session.add(gene)
        await session.flush()
        cap = CapabilityMarketEntry(
            name=f"cap-{_uid()}", type="skill", scope="org",
            organization_id=bundle.org.id, created_via="manual",
        )
        session.add(cap)
        await session.flush()
        entity = Entity(namespace_id=ns.id, slug=f"en-{_uid()}", name="Source")
        session.add(entity)
        await session.flush()
        session.add(EntityAiGene(entity_id=entity.id, ai_gene_id=gene.id))
        session.add(EntityCapability(entity_id=entity.id, capability_id=cap.id))
        await session.commit()

        resp = client.post(f"/api/v1/entities/{entity.id}/clone", headers=headers, json={})
        assert resp.status_code == 201, resp.text
        new_id = resp.json()["id"]
        assert new_id != entity.id

        engine, factory = await _verify_session(db_url)
        try:
            async with factory() as verify:
                new_genes = (await verify.execute(select(EntityAiGene).where(
                    EntityAiGene.entity_id == new_id, EntityAiGene.deleted_at.is_(None)
                ))).scalars().all()
                assert len(new_genes) == 1
                new_caps = (await verify.execute(select(EntityCapability).where(
                    EntityCapability.entity_id == new_id, EntityCapability.deleted_at.is_(None)
                ))).scalars().all()
                assert len(new_caps) == 1

                from app.models.event import Event

                events = (await verify.execute(select(Event).where(
                    Event.type == "entity.cloned"
                ))).scalars().all()
                assert len(events) == 1
                assert events[0].payload["source_id"] == entity.id
                assert events[0].payload["new_id"] == new_id
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_clone_no_instance_copied(
        self, client: TestClient, session: AsyncSession, create_org_bundle,
        namespace_factory, db_url: str
    ) -> None:
        from app.models.instance import InstanceStatus

        _register(client, f"en-ni-sa-{_uid()}", f"en-ni-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"en-ni-m-{_uid()}", f"en-ni-m-{_uid()}@t.co")
        ns = await namespace_factory()
        bundle = await create_org_bundle(
            member_id, atoms=("can_clone_entity", "can_manage_namespace"), namespace=ns,
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        entity = Entity(namespace_id=ns.id, slug=f"en-ni-{_uid()}", name="E")
        session.add(entity)
        await session.flush()
        ws = Workspace(namespace_id=ns.id, slug=f"ws-ni-{_uid()}", name="WS")
        session.add(ws)
        await session.flush()
        session.add(Instance(entity_id=entity.id, workspace_id=ws.id,
                            status=InstanceStatus.running.value, proxy_token=str(uuid.uuid4())))
        await session.commit()

        resp = client.post(f"/api/v1/entities/{entity.id}/clone", headers=headers, json={})
        assert resp.status_code == 201, resp.text
        new_id = resp.json()["id"]

        engine, factory = await _verify_session(db_url)
        try:
            async with factory() as verify:
                new_instances = (await verify.execute(select(Instance).where(
                    Instance.entity_id == new_id, Instance.deleted_at.is_(None)
                ))).scalars().all()
                assert new_instances == []
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_clone_without_permission_403(
        self, client: TestClient, session: AsyncSession, create_org_bundle, namespace_factory
    ) -> None:
        _register(client, f"en-np-sa-{_uid()}", f"en-np-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"en-np-m-{_uid()}", f"en-np-m-{_uid()}@t.co")
        ns = await namespace_factory()
        bundle = await create_org_bundle(member_id, atoms=("can_view_workspace",), namespace=ns)
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        entity = Entity(namespace_id=ns.id, slug=f"en-np-{_uid()}", name="E")
        session.add(entity)
        await session.commit()

        resp = client.post(f"/api/v1/entities/{entity.id}/clone", headers=headers, json={})
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"


# ---------------------------------------------------------------------------
# Organization clone
# ---------------------------------------------------------------------------


class TestCloneOrganization:
    @pytest.mark.asyncio
    async def test_clone_creates_new_org_with_structure(
        self, client: TestClient, session: AsyncSession, create_org_bundle, db_url: str
    ) -> None:
        _register(client, f"og-sa-{_uid()}", f"og-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"og-m-{_uid()}", f"og-m-{_uid()}@t.co")
        bundle = await create_org_bundle(
            member_id, atoms=("can_clone_organization", "can_manage_organization")
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        ns = Namespace(org_id=bundle.org.id, slug=f"ns-1-{_uid()}", name="NS One")
        session.add(ns)
        await session.flush()
        ws = Workspace(namespace_id=ns.id, slug="ws-1", name="WS One")
        session.add(ws)
        await session.flush()
        entity = Entity(namespace_id=ns.id, slug="en-1", name="Entity One")
        session.add(entity)
        await session.commit()

        resp = client.post(
            f"/api/v1/organizations/{bundle.org.id}/clone", headers=headers, json={}
        )
        assert resp.status_code == 201, resp.text
        new_org_id = resp.json()["id"]
        assert new_org_id != bundle.org.id

        engine, factory = await _verify_session(db_url)
        try:
            async with factory() as verify:
                new_org = await verify.get(Organization, new_org_id)
                assert new_org is not None
                assert new_org.slug != bundle.org.slug
                assert new_org.system_hub_provider_id is None

                new_namespaces = (await verify.execute(select(Namespace).where(
                    Namespace.org_id == new_org_id, Namespace.deleted_at.is_(None)
                ))).scalars().all()
                ns_slugs = {n.slug for n in new_namespaces}
                assert ns.slug in ns_slugs

                target_ns = next(n for n in new_namespaces if n.slug == ns.slug)
                new_ws = (await verify.execute(select(Workspace).where(
                    Workspace.namespace_id == target_ns.id, Workspace.deleted_at.is_(None)
                ))).scalars().all()
                assert len(new_ws) == 1

                new_entities = (await verify.execute(select(Entity).where(
                    Entity.namespace_id == target_ns.id, Entity.deleted_at.is_(None)
                ))).scalars().all()
                assert len(new_entities) == 1

                new_instances = (await verify.execute(select(Instance).where(
                    Instance.workspace_id == new_ws[0].id, Instance.deleted_at.is_(None)
                ))).scalars().all()
                assert new_instances == []

                from app.models.event import Event

                events = (await verify.execute(select(Event).where(
                    Event.type == "organization.cloned"
                ))).scalars().all()
                assert len(events) == 1
                assert events[0].payload["source_id"] == bundle.org.id
                assert events[0].payload["new_id"] == new_org_id
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_clone_only_caller_has_org_contract(
        self, client: TestClient, session: AsyncSession, create_org_bundle, db_url: str
    ) -> None:
        _register(client, f"og-oc-sa-{_uid()}", f"og-oc-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"og-oc-m-{_uid()}", f"og-oc-m-{_uid()}@t.co")
        bundle = await create_org_bundle(
            member_id, atoms=("can_clone_organization", "can_manage_organization")
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        resp = client.post(
            f"/api/v1/organizations/{bundle.org.id}/clone", headers=headers, json={}
        )
        assert resp.status_code == 201, resp.text
        new_org_id = resp.json()["id"]

        engine, factory = await _verify_session(db_url)
        try:
            async with factory() as verify:
                contracts = (await verify.execute(select(OrganizationContract).where(
                    OrganizationContract.organization_id == new_org_id,
                    OrganizationContract.deleted_at.is_(None)
                ))).scalars().all()
                assert len(contracts) == 1
                assert contracts[0].user_id == member_id
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_clone_zero_copied_org_contracts(
        self, client: TestClient, session: AsyncSession, create_org_bundle, db_url: str
    ) -> None:
        _register(client, f"og-zc-sa-{_uid()}", f"og-zc-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"og-zc-m-{_uid()}", f"og-zc-m-{_uid()}@t.co")
        bundle = await create_org_bundle(
            member_id, atoms=("can_clone_organization", "can_manage_organization")
        )
        other_token, other_id = _register(client, f"og-zc-o-{_uid()}", f"og-zc-o-{_uid()}@t.co")
        client.post(
            f"/api/v1/organizations/{bundle.org.id}/members", headers=_auth(token),
            json={"user_id": other_id, "atom_slugs": ["can_view_workspace"]},
        )

        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}
        resp = client.post(
            f"/api/v1/organizations/{bundle.org.id}/clone", headers=headers, json={}
        )
        assert resp.status_code == 201, resp.text
        new_org_id = resp.json()["id"]

        engine, factory = await _verify_session(db_url)
        try:
            async with factory() as verify:
                contracts = (await verify.execute(select(OrganizationContract).where(
                    OrganizationContract.organization_id == new_org_id,
                    OrganizationContract.deleted_at.is_(None)
                ))).scalars().all()
                assert len(contracts) == 1
                assert contracts[0].user_id == member_id
                assert all(c.user_id != other_id for c in contracts)
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_clone_zero_namespace_contracts(
        self, client: TestClient, session: AsyncSession, create_org_bundle, db_url: str
    ) -> None:
        _register(client, f"og-zn-sa-{_uid()}", f"og-zn-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"og-zn-m-{_uid()}", f"og-zn-m-{_uid()}@t.co")
        bundle = await create_org_bundle(
            member_id, atoms=("can_clone_organization", "can_manage_organization")
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        ns = Namespace(org_id=bundle.org.id, slug=f"ns-zn-{_uid()}", name="NS")
        session.add(ns)
        await session.commit()

        resp = client.post(
            f"/api/v1/organizations/{bundle.org.id}/clone", headers=headers, json={}
        )
        assert resp.status_code == 201, resp.text
        new_org_id = resp.json()["id"]

        engine, factory = await _verify_session(db_url)
        try:
            async with factory() as verify:
                new_ns = (await verify.execute(select(Namespace).where(
                    Namespace.org_id == new_org_id, Namespace.deleted_at.is_(None)
                ))).scalars().all()
                new_ns_ids = [n.id for n in new_ns]
                ns_contracts = (await verify.execute(select(NamespaceContract).where(
                    NamespaceContract.namespace_id.in_(new_ns_ids),
                    NamespaceContract.deleted_at.is_(None)
                ))).scalars().all()
                assert ns_contracts == []
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_clone_other_members_cannot_see_new_org(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(client, f"og-om-sa-{_uid()}", f"og-om-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"og-om-m-{_uid()}", f"og-om-m-{_uid()}@t.co")
        bundle = await create_org_bundle(
            member_id, atoms=("can_clone_organization", "can_manage_organization")
        )
        other_token, other_id = _register(client, f"og-om-o-{_uid()}", f"og-om-o-{_uid()}@t.co")
        client.post(
            f"/api/v1/organizations/{bundle.org.id}/members", headers=_auth(token),
            json={"user_id": other_id, "atom_slugs": ["can_view_workspace"]},
        )

        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}
        resp = client.post(
            f"/api/v1/organizations/{bundle.org.id}/clone", headers=headers, json={}
        )
        assert resp.status_code == 201, resp.text
        new_org_id = resp.json()["id"]

        listed = client.get("/api/v1/organizations", headers=_auth(other_token))
        assert listed.status_code == 200
        ids = {item["id"] for item in listed.json()["items"]}
        assert new_org_id not in ids

        direct = client.get(f"/api/v1/organizations/{new_org_id}", headers=_auth(other_token))
        assert direct.status_code == 404

    @pytest.mark.asyncio
    async def test_clone_no_instances_copied(
        self, client: TestClient, session: AsyncSession, create_org_bundle, db_url: str
    ) -> None:
        from app.models.instance import InstanceStatus

        _register(client, f"og-ni-sa-{_uid()}", f"og-ni-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"og-ni-m-{_uid()}", f"og-ni-m-{_uid()}@t.co")
        bundle = await create_org_bundle(
            member_id, atoms=("can_clone_organization", "can_manage_organization")
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        ns = Namespace(org_id=bundle.org.id, slug=f"ns-ni-{_uid()}", name="NS")
        session.add(ns)
        await session.flush()
        ws = Workspace(namespace_id=ns.id, slug="ws-ni", name="WS")
        session.add(ws)
        await session.flush()
        entity = Entity(namespace_id=ns.id, slug="en-ni", name="E")
        session.add(entity)
        await session.flush()
        session.add(Instance(entity_id=entity.id, workspace_id=ws.id,
                             status=InstanceStatus.running.value, proxy_token=str(uuid.uuid4())))
        await session.commit()

        resp = client.post(
            f"/api/v1/organizations/{bundle.org.id}/clone", headers=headers, json={}
        )
        assert resp.status_code == 201, resp.text
        new_org_id = resp.json()["id"]

        engine, factory = await _verify_session(db_url)
        try:
            async with factory() as verify:
                new_ns = (await verify.execute(select(Namespace).where(
                    Namespace.org_id == new_org_id, Namespace.deleted_at.is_(None)
                ))).scalars().all()
                new_ns_ids = [n.id for n in new_ns]
                new_ws = (await verify.execute(select(Workspace).where(
                    Workspace.namespace_id.in_(new_ns_ids), Workspace.deleted_at.is_(None)
                ))).scalars().all()
                new_ws_ids = [w.id for w in new_ws]
                instances = (await verify.execute(select(Instance).where(
                    Instance.workspace_id.in_(new_ws_ids), Instance.deleted_at.is_(None)
                ))).scalars().all()
                assert instances == []
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_clone_without_permission_403(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(client, f"og-np-sa-{_uid()}", f"og-np-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"og-np-m-{_uid()}", f"og-np-m-{_uid()}@t.co")
        bundle = await create_org_bundle(member_id, atoms=("can_view_workspace",))
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        resp = client.post(
            f"/api/v1/organizations/{bundle.org.id}/clone", headers=headers, json={}
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

    @pytest.mark.asyncio
    async def test_clone_copies_org_base_classes_with_junctions(
        self, client: TestClient, session: AsyncSession, create_org_bundle, db_url: str
    ) -> None:
        from app.models.ai_gene import AiGene
        from app.models.base_class import BaseClass
        from app.models.capability_market import CapabilityMarketEntry

        _register(client, f"og-bc-sa-{_uid()}", f"og-bc-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"og-bc-m-{_uid()}", f"og-bc-m-{_uid()}@t.co")
        bundle = await create_org_bundle(
            member_id, atoms=("can_clone_organization", "can_manage_organization")
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        bc = BaseClass(slug=f"bc-{_uid()}", name="Org BC", scope="org",
                       organization_id=bundle.org.id)
        session.add(bc)
        await session.flush()
        gene = AiGene(slug=f"gene-{_uid()}", name="G", scope="org", organization_id=bundle.org.id)
        session.add(gene)
        await session.flush()
        cap = CapabilityMarketEntry(
            name=f"cap-{_uid()}", type="skill", scope="org",
            organization_id=bundle.org.id, created_via="manual",
        )
        session.add(cap)
        await session.flush()
        session.add(BaseClassAiGene(base_class_id=bc.id, ai_gene_id=gene.id))
        session.add(BaseClassCapability(base_class_id=bc.id, capability_id=cap.id))
        await session.commit()

        resp = client.post(
            f"/api/v1/organizations/{bundle.org.id}/clone", headers=headers, json={}
        )
        assert resp.status_code == 201, resp.text
        new_org_id = resp.json()["id"]

        engine, factory = await _verify_session(db_url)
        try:
            async with factory() as verify:
                new_bcs = (await verify.execute(select(BaseClass).where(
                    BaseClass.organization_id == new_org_id,
                    BaseClass.deleted_at.is_(None),
                ))).scalars().all()
                assert len(new_bcs) == 1
                new_bc = new_bcs[0]
                assert new_bc.slug != bc.slug

                new_gene_links = (await verify.execute(select(BaseClassAiGene).where(
                    BaseClassAiGene.base_class_id == new_bc.id,
                    BaseClassAiGene.deleted_at.is_(None),
                ))).scalars().all()
                assert len(new_gene_links) == 1
                src_gene_links = (await verify.execute(select(BaseClassAiGene).where(
                    BaseClassAiGene.base_class_id == bc.id,
                    BaseClassAiGene.deleted_at.is_(None),
                ))).scalars().all()
                assert new_gene_links[0].id != src_gene_links[0].id
                assert new_gene_links[0].ai_gene_id == src_gene_links[0].ai_gene_id

                new_cap_links = (await verify.execute(select(BaseClassCapability).where(
                    BaseClassCapability.base_class_id == new_bc.id,
                    BaseClassCapability.deleted_at.is_(None),
                ))).scalars().all()
                assert len(new_cap_links) == 1
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_clone_large_org_sets_statement_timeout(
        self, client: TestClient, session: AsyncSession, create_org_bundle,
        monkeypatch: pytest.MonkeyPatch, db_url: str
    ) -> None:
        import app.services.clone as clone_mod
        from app.core.security import hash_password
        from app.models.user import User

        _register(client, f"og-to-sa-{_uid()}", f"og-to-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"og-to-m-{_uid()}", f"og-to-m-{_uid()}@t.co")
        bundle = await create_org_bundle(
            member_id, atoms=("can_clone_organization", "can_manage_organization")
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        ns = Namespace(org_id=bundle.org.id, slug=f"ns-to-{_uid()}", name="NS")
        session.add(ns)
        await session.flush()
        ws = Workspace(namespace_id=ns.id, slug=f"ws-to-{_uid()}", name="WS")
        session.add(ws)
        await session.flush()

        # Lower the threshold so a small org trips the SET LOCAL branch.
        monkeypatch.setattr(clone_mod, "_LARGE_ORG_THRESHOLD", 1)
        b_user = User(username=f"og-to-b-{_uid()}", email=f"og-to-b-{_uid()}@t.co",
                      password_hash=hash_password("p"))
        session.add(b_user)
        await session.flush()
        mem_a = Membership(workspace_id=ws.id, user_id=member_id, posx=0, posy=0)
        mem_b = Membership(workspace_id=ws.id, user_id=b_user.id, posx=120, posy=0)
        session.add_all([mem_a, mem_b])
        await session.flush()
        ids = sorted([mem_a.id, mem_b.id])
        session.add(Passage(workspace_id=ws.id, from_membership_id=ids[0],
                            to_membership_id=ids[1], is_active=True, mode="dual"))
        await session.commit()

        resp = client.post(
            f"/api/v1/organizations/{bundle.org.id}/clone", headers=headers, json={}
        )
        assert resp.status_code == 201, resp.text
        new_org_id = resp.json()["id"]

        engine, factory = await _verify_session(db_url)
        try:
            async with factory() as verify:
                new_ws = (await verify.execute(select(Workspace).where(
                    Workspace.namespace_id.in_(
                        select(Namespace.id).where(
                            Namespace.org_id == new_org_id, Namespace.deleted_at.is_(None)
                        )
                    ),
                    Workspace.deleted_at.is_(None),
                ))).scalars().all()
                assert len(new_ws) == 1
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_clone_deep_copies_provider_bindings(
        self, client: TestClient, session: AsyncSession, create_org_bundle, db_url: str
    ) -> None:
        from app.models.organization_provider import OrganizationProvider

        _register(client, f"og-pv-sa-{_uid()}", f"og-pv-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"og-pv-m-{_uid()}", f"og-pv-m-{_uid()}@t.co")
        bundle = await create_org_bundle(
            member_id, atoms=("can_clone_organization", "can_manage_organization")
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        hub_prov = OrganizationProvider(
            organization_id=bundle.org.id, origin="custom", name="Hub Provider",
            slug="hub-prov", request_format="completion",
            base_url="https://hub.example.com", api_key_ref="sk-hub-1",
            default_model="gpt-4o",
        )
        session.add(hub_prov)
        await session.flush()
        cereb_prov = OrganizationProvider(
            organization_id=bundle.org.id, origin="custom", name="Cereb Provider",
            slug="cereb-prov", request_format="anthropic",
            base_url="https://cereb.example.com", api_key_ref="sk-cereb-1",
            default_model="claude-sonnet",
        )
        session.add(cereb_prov)
        await session.flush()
        bundle.org.system_hub_provider_id = hub_prov.id
        bundle.org.system_hub_model = "gpt-4o"
        bundle.org.cerebellum_default_provider_id = cereb_prov.id
        bundle.org.cerebellum_default_model = "claude-sonnet"
        bundle.org.use_proxy = True
        bundle.org.proxy_host = "proxy.example.com"
        bundle.org.proxy_port = 8080
        bundle.org.proxy_username = "user"
        bundle.org.proxy_password = "secret"
        await session.commit()

        resp = client.post(
            f"/api/v1/organizations/{bundle.org.id}/clone", headers=headers, json={}
        )
        assert resp.status_code == 201, resp.text
        new_org_id = resp.json()["id"]

        engine, factory = await _verify_session(db_url)
        try:
            async with factory() as verify:
                new_org = await verify.get(Organization, new_org_id)
                assert new_org is not None
                assert new_org.system_hub_provider_id is not None
                assert new_org.system_hub_provider_id != hub_prov.id
                assert new_org.cerebellum_default_provider_id != cereb_prov.id
                assert new_org.system_hub_model == "gpt-4o"
                assert new_org.cerebellum_default_model == "claude-sonnet"
                assert new_org.use_proxy is True
                assert new_org.proxy_host == "proxy.example.com"
                assert new_org.proxy_port == 8080
                assert new_org.proxy_password == "secret"

                new_providers = (await verify.execute(select(OrganizationProvider).where(
                    OrganizationProvider.organization_id == new_org_id,
                    OrganizationProvider.deleted_at.is_(None),
                ))).scalars().all()
                assert len(new_providers) == 2
                by_slug = {p.slug: p for p in new_providers}
                assert by_slug["hub-prov"].api_key_ref == "sk-hub-1"
                assert by_slug["hub-prov"].id == new_org.system_hub_provider_id
                assert by_slug["cereb-prov"].api_key_ref == "sk-cereb-1"
                assert by_slug["cereb-prov"].id == new_org.cerebellum_default_provider_id

                src_providers = (await verify.execute(select(OrganizationProvider).where(
                    OrganizationProvider.organization_id == bundle.org.id,
                    OrganizationProvider.deleted_at.is_(None),
                ))).scalars().all()
                assert len(src_providers) == 2
        finally:
            await engine.dispose()


# ---------------------------------------------------------------------------
# Workspace clone
# ---------------------------------------------------------------------------


class TestCloneWorkspace:
    @pytest.mark.asyncio
    async def test_clone_awakened_induced_subgraph(
        self, client: TestClient, session: AsyncSession, create_org_bundle,
        namespace_factory, db_url: str
    ) -> None:
        from app.core.security import hash_password
        from app.models.user import User

        _register(client, f"ws-sa-{_uid()}", f"ws-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"ws-m-{_uid()}", f"ws-m-{_uid()}@t.co")
        ns = await namespace_factory()
        bundle = await create_org_bundle(
            member_id, atoms=("can_clone_workspace", "can_manage_workspace"), namespace=ns,
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        ws = Workspace(namespace_id=ns.id, slug=f"ws-{_uid()}", name="WS")
        session.add(ws)
        await session.flush()

        b_user = User(username=f"ws-b-{_uid()}", email=f"ws-b-{_uid()}@t.co",
                      password_hash=hash_password("p"))
        session.add(b_user)
        await session.flush()

        mem_a = Membership(workspace_id=ws.id, user_id=member_id, posx=0, posy=0)
        mem_b = Membership(workspace_id=ws.id, user_id=b_user.id, posx=120, posy=0)
        session.add_all([mem_a, mem_b])
        await session.flush()

        ids = sorted([mem_a.id, mem_b.id])
        session.add(Passage(workspace_id=ws.id, from_membership_id=ids[0],
                            to_membership_id=ids[1], is_active=True, mode="dual"))
        await session.commit()

        resp = client.post(f"/api/v1/workspaces/{ws.id}/clone", headers=headers, json={})
        assert resp.status_code == 201, resp.text
        new_ws_id = resp.json()["id"]

        engine, factory = await _verify_session(db_url)
        try:
            async with factory() as verify:
                new_mems = (await verify.execute(select(Membership).where(
                    Membership.workspace_id == new_ws_id, Membership.deleted_at.is_(None)
                ))).scalars().all()
                assert len(new_mems) == 2
                assert all(m.user_id is not None for m in new_mems)
                assert all(m.instance_id is None for m in new_mems)

                new_passages = (await verify.execute(select(Passage).where(
                    Passage.workspace_id == new_ws_id, Passage.deleted_at.is_(None)
                ))).scalars().all()
                assert len(new_passages) == 1

                hub = (await verify.execute(select(CentralHub).where(
                    CentralHub.workspace_id == new_ws_id, CentralHub.deleted_at.is_(None)
                ))).scalars().all()
                assert len(hub) == 1
                vault = (await verify.execute(select(Vault).where(
                    Vault.workspace_id == new_ws_id, Vault.deleted_at.is_(None)
                ))).scalars().all()
                assert len(vault) == 1

                from app.models.event import Event

                events = (await verify.execute(select(Event).where(
                    Event.type == "workspace.cloned"
                ))).scalars().all()
                assert len(events) == 1
                assert events[0].payload["source_id"] == ws.id
                assert events[0].payload["new_id"] == new_ws_id
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_clone_counterexample_a_lost_c_no_edge(
        self, client: TestClient, session: AsyncSession, create_org_bundle,
        namespace_factory, db_url: str
    ) -> None:
        from app.core.security import hash_password
        from app.models.instance import InstanceStatus
        from app.models.user import User

        _register(client, f"ws-cl-sa-{_uid()}", f"ws-cl-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"ws-cl-m-{_uid()}", f"ws-cl-m-{_uid()}@t.co")
        ns = await namespace_factory()
        bundle = await create_org_bundle(
            member_id, atoms=("can_clone_workspace", "can_manage_workspace"), namespace=ns,
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        ws = Workspace(namespace_id=ns.id, slug=f"wscl-{_uid()}", name="WS")
        session.add(ws)
        await session.flush()

        entity = Entity(namespace_id=ns.id, slug=f"en-cl-{_uid()}", name="E")
        session.add(entity)
        await session.flush()
        inst = Instance(entity_id=entity.id, workspace_id=ws.id,
                        status=InstanceStatus.running.value, proxy_token=str(uuid.uuid4()))
        session.add(inst)
        await session.flush()

        c_user = User(username=f"ws-c-{_uid()}", email=f"ws-c-{_uid()}@t.co",
                      password_hash=hash_password("p"))
        session.add(c_user)
        await session.flush()

        mem_a = Membership(workspace_id=ws.id, user_id=member_id, posx=0, posy=0)
        mem_b = Membership(workspace_id=ws.id, instance_id=inst.id, posx=120, posy=0)
        mem_c = Membership(workspace_id=ws.id, user_id=c_user.id, posx=240, posy=0)
        session.add_all([mem_a, mem_b, mem_c])
        await session.flush()

        ab = sorted([mem_a.id, mem_b.id])
        bc = sorted([mem_b.id, mem_c.id])
        session.add(Passage(workspace_id=ws.id, from_membership_id=ab[0],
                            to_membership_id=ab[1], is_active=True, mode="dual"))
        session.add(Passage(workspace_id=ws.id, from_membership_id=bc[0],
                            to_membership_id=bc[1], is_active=True, mode="dual"))
        await session.commit()

        resp = client.post(f"/api/v1/workspaces/{ws.id}/clone", headers=headers, json={})
        assert resp.status_code == 201, resp.text
        new_ws_id = resp.json()["id"]

        engine, factory = await _verify_session(db_url)
        try:
            async with factory() as verify:
                new_mems = (await verify.execute(select(Membership).where(
                    Membership.workspace_id == new_ws_id, Membership.deleted_at.is_(None)
                ))).scalars().all()
                assert len(new_mems) == 2
                assert all(m.instance_id is None for m in new_mems)

                new_passages = (await verify.execute(select(Passage).where(
                    Passage.workspace_id == new_ws_id, Passage.deleted_at.is_(None)
                ))).scalars().all()
                assert new_passages == []
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_clone_dropped_passage_events(
        self, client: TestClient, session: AsyncSession, create_org_bundle,
        namespace_factory, db_url: str
    ) -> None:
        from app.models.event import Event
        from app.models.instance import InstanceStatus

        _register(client, f"ws-dp-sa-{_uid()}", f"ws-dp-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"ws-dp-m-{_uid()}", f"ws-dp-m-{_uid()}@t.co")
        ns = await namespace_factory()
        bundle = await create_org_bundle(
            member_id, atoms=("can_clone_workspace", "can_manage_workspace"), namespace=ns,
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        ws = Workspace(namespace_id=ns.id, slug=f"wsdp-{_uid()}", name="WS")
        session.add(ws)
        await session.flush()

        entity = Entity(namespace_id=ns.id, slug=f"en-dp-{_uid()}", name="E")
        session.add(entity)
        await session.flush()
        inst = Instance(entity_id=entity.id, workspace_id=ws.id,
                        status=InstanceStatus.running.value, proxy_token=str(uuid.uuid4()))
        session.add(inst)
        await session.flush()

        mem_a = Membership(workspace_id=ws.id, user_id=member_id, posx=0, posy=0)
        mem_b = Membership(workspace_id=ws.id, instance_id=inst.id, posx=120, posy=0)
        session.add_all([mem_a, mem_b])
        await session.flush()

        ab = sorted([mem_a.id, mem_b.id])
        dropped_passage = Passage(workspace_id=ws.id, from_membership_id=ab[0],
                                  to_membership_id=ab[1], is_active=True, mode="dual")
        session.add(dropped_passage)
        await session.commit()
        dropped_source_id = dropped_passage.id

        resp = client.post(f"/api/v1/workspaces/{ws.id}/clone", headers=headers, json={})
        assert resp.status_code == 201, resp.text

        engine, factory = await _verify_session(db_url)
        try:
            async with factory() as verify:
                events = (await verify.execute(select(Event).where(
                    Event.type == "workspace.clone_passage_dropped"
                ))).scalars().all()
                assert len(events) == 1
                assert events[0].payload["source_passage_id"] == dropped_source_id
                assert events[0].payload["reason"] == "lost_endpoint"
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_clone_no_instances_copied(
        self, client: TestClient, session: AsyncSession, create_org_bundle,
        namespace_factory, db_url: str
    ) -> None:
        from app.models.instance import InstanceStatus

        _register(client, f"ws-ni-sa-{_uid()}", f"ws-ni-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"ws-ni-m-{_uid()}", f"ws-ni-m-{_uid()}@t.co")
        ns = await namespace_factory()
        bundle = await create_org_bundle(
            member_id, atoms=("can_clone_workspace", "can_manage_workspace"), namespace=ns,
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        ws = Workspace(namespace_id=ns.id, slug=f"wsni-{_uid()}", name="WS")
        session.add(ws)
        await session.flush()

        entity = Entity(namespace_id=ns.id, slug=f"en-ni-{_uid()}", name="E")
        session.add(entity)
        await session.flush()
        inst = Instance(entity_id=entity.id, workspace_id=ws.id,
                        status=InstanceStatus.running.value, proxy_token=str(uuid.uuid4()))
        session.add(inst)
        await session.flush()
        session.add(Membership(workspace_id=ws.id, instance_id=inst.id, posx=0, posy=0))
        await session.commit()

        resp = client.post(f"/api/v1/workspaces/{ws.id}/clone", headers=headers, json={})
        assert resp.status_code == 201, resp.text
        new_ws_id = resp.json()["id"]

        engine, factory = await _verify_session(db_url)
        try:
            async with factory() as verify:
                new_instances = (await verify.execute(select(Instance).where(
                    Instance.workspace_id == new_ws_id, Instance.deleted_at.is_(None)
                ))).scalars().all()
                assert new_instances == []
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_clone_without_permission_403(
        self, client: TestClient, session: AsyncSession, create_org_bundle, namespace_factory
    ) -> None:
        _register(client, f"ws-np-sa-{_uid()}", f"ws-np-sa-{_uid()}@t.co")
        token, member_id = _register(client, f"ws-np-m-{_uid()}", f"ws-np-m-{_uid()}@t.co")
        ns = await namespace_factory()
        bundle = await create_org_bundle(member_id, atoms=("can_view_workspace",), namespace=ns)
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        ws = Workspace(namespace_id=ns.id, slug=f"wsnp-{_uid()}", name="WS")
        session.add(ws)
        await session.commit()

        resp = client.post(f"/api/v1/workspaces/{ws.id}/clone", headers=headers, json={})
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"


# ---------------------------------------------------------------------------
# Instance clone rejected
# ---------------------------------------------------------------------------


class TestInstanceCloneRejected:
    def test_instance_clone_returns_404(self, client: TestClient) -> None:
        _register(client, f"ic-sa-{_uid()}", f"ic-sa-{_uid()}@t.co")
        token, _ = _register(client, f"ic-m-{_uid()}", f"ic-m-{_uid()}@t.co")
        resp = client.post(
            f"/api/v1/instances/{uuid.uuid4()}/clone", headers=_auth(token), json={}
        )
        assert resp.status_code == 404
