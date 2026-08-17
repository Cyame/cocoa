"""v4.1 capability / gene CRUD and attach gates."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.core.gene_atoms import ATOM_CATALOG
from app.models.capability_market import CapabilityMarketEntry
from app.models.junctions import EntityCapability
from app.models.organization import Organization


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, username: str, email: str) -> tuple[str, str]:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": email,
            "password": "password123",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["id"]


class TestCapabilityMarketCrud:
    @pytest.mark.asyncio
    async def test_member_can_list_without_manage_atom(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(client, f"v41-a-{uuid.uuid4().hex[:6]}", f"v41-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"v41-m-{uuid.uuid4().hex[:6]}", f"v41-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle = await create_org_bundle(member_id, atoms=("can_view_workspace",))
        resp = client.get(
            "/api/v1/capability-market",
            headers={
                **_auth(member_token),
                "X-Organization-Id": bundle.org.id,
            },
        )
        assert resp.status_code == 200
        assert "items" in resp.json()

    @pytest.mark.asyncio
    async def test_post_without_manage_atom_forbidden(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(client, f"v41-a-{uuid.uuid4().hex[:6]}", f"v41-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"v41-m-{uuid.uuid4().hex[:6]}", f"v41-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle = await create_org_bundle(member_id, atoms=("can_view_workspace",))
        resp = client.post(
            "/api/v1/capability-market",
            headers={
                **_auth(member_token),
                "X-Organization-Id": bundle.org.id,
            },
            json={
                "name": f"cap-{uuid.uuid4().hex[:8]}",
                "type": "skill",
                "scope": "org",
            },
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

    @pytest.mark.asyncio
    async def test_post_with_manage_capabilities_sets_org_id(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(client, f"v41-a-{uuid.uuid4().hex[:6]}", f"v41-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"v41-m-{uuid.uuid4().hex[:6]}", f"v41-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle = await create_org_bundle(
            member_id, atoms=("can_manage_capabilities",)
        )
        name = f"cap-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            "/api/v1/capability-market",
            headers={
                **_auth(member_token),
                "X-Organization-Id": bundle.org.id,
            },
            json={"name": name, "type": "skill", "scope": "org"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["organization_id"] == bundle.org.id
        assert body["scope"] == "org"
        assert body["created_via"] == "manual"

    @pytest.mark.asyncio
    async def test_system_scope_create_forbidden(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        admin_token, admin_id = _register(
            client, f"v41-a-{uuid.uuid4().hex[:6]}", f"v41-a-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle = await create_org_bundle(
            admin_id, atoms=("can_manage_capabilities",)
        )
        resp = client.post(
            "/api/v1/capability-market",
            headers={
                **_auth(admin_token),
                "X-Organization-Id": bundle.org.id,
            },
            json={
                "name": f"sys-cap-{uuid.uuid4().hex[:8]}",
                "type": "skill",
                "scope": "system",
            },
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "scope.system_create_forbidden"

    @pytest.mark.asyncio
    async def test_list_filtered_by_org(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        admin_token, admin_id = _register(
            client, f"v41-a-{uuid.uuid4().hex[:6]}", f"v41-a-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle_a = await create_org_bundle(
            admin_id, atoms=("can_manage_capabilities",)
        )
        org_b = Organization(slug=f"org-b-{uuid.uuid4().hex[:6]}", name="Org B")
        session.add(org_b)
        await session.flush()
        cap_a = CapabilityMarketEntry(
            name=f"cap-a-{uuid.uuid4().hex[:8]}",
            type="skill",
            scope="org",
            organization_id=bundle_a.org.id,
            created_via="manual",
        )
        cap_b = CapabilityMarketEntry(
            name=f"cap-b-{uuid.uuid4().hex[:8]}",
            type="skill",
            scope="org",
            organization_id=org_b.id,
            created_via="manual",
        )
        session.add_all([cap_a, cap_b])
        await session.commit()

        resp = client.get(
            "/api/v1/capability-market",
            headers={
                **_auth(admin_token),
                "X-Organization-Id": bundle_a.org.id,
            },
        )
        assert resp.status_code == 200
        names = {item["name"] for item in resp.json()["items"]}
        assert cap_a.name in names
        assert cap_b.name not in names


class TestAiGeneCrud:
    @pytest.mark.asyncio
    async def test_ai_gene_cud_with_manage_ai_genes(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(client, f"v41-a-{uuid.uuid4().hex[:6]}", f"v41-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"v41-m-{uuid.uuid4().hex[:6]}", f"v41-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle = await create_org_bundle(member_id, atoms=("can_manage_ai_genes",))
        slug = f"gene-{uuid.uuid4().hex[:8]}"
        created = client.post(
            "/api/v1/ai-genes",
            headers={
                **_auth(member_token),
                "X-Organization-Id": bundle.org.id,
            },
            json={"slug": slug, "name": "Test Gene", "scope": "org"},
        )
        assert created.status_code == 201, created.text
        gene_id = created.json()["id"]
        assert created.json()["organization_id"] == bundle.org.id

        patched = client.patch(
            f"/api/v1/ai-genes/{gene_id}",
            headers={
                **_auth(member_token),
                "X-Organization-Id": bundle.org.id,
            },
            json={"name": "Renamed"},
        )
        assert patched.status_code == 200
        assert patched.json()["name"] == "Renamed"

        deleted = client.delete(
            f"/api/v1/ai-genes/{gene_id}",
            headers={
                **_auth(member_token),
                "X-Organization-Id": bundle.org.id,
            },
        )
        assert deleted.status_code == 204


class TestEntityAttachDetach:
    @pytest.mark.asyncio
    async def test_detach_soft_deletes_junction_and_bumps_hash(
        self,
        client: TestClient,
        session: AsyncSession,
        entity_factory,
        namespace_factory,
        create_org_bundle,
    ) -> None:
        _register(client, f"v41-a-{uuid.uuid4().hex[:6]}", f"v41-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"v41-m-{uuid.uuid4().hex[:6]}", f"v41-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"v41-ns-{uuid.uuid4().hex[:6]}")
        await create_org_bundle(
            member_id,
            atoms=("can_manage_capabilities", "can_manage_namespace"),
            namespace=ns,
        )
        entity = await entity_factory(namespace_id=ns.id)
        cap = CapabilityMarketEntry(
            name=f"ent-cap-{uuid.uuid4().hex[:8]}",
            type="skill",
            scope="org",
            organization_id=ns.org_id,
            created_via="manual",
        )
        session.add(cap)
        await session.flush()
        hash_before = entity.migration_hash
        await session.commit()

        attach = client.post(
            f"/api/v1/entities/{entity.id}/capabilities",
            headers=_auth(member_token),
            json={"capability_id": cap.id},
        )
        assert attach.status_code == 201, attach.text

        detach = client.delete(
            f"/api/v1/entities/{entity.id}/capabilities/{cap.id}",
            headers=_auth(member_token),
        )
        assert detach.status_code == 204

        link = (
            await session.execute(
                select(EntityCapability).where(
                    EntityCapability.entity_id == entity.id,
                    EntityCapability.capability_id == cap.id,
                )
            )
        ).scalar_one()
        assert link.deleted_at is not None

        await session.refresh(entity)
        assert entity.migration_hash != hash_before


class TestGenePackSeeds:
    def test_pack_slugs_subset_of_atom_catalog(self) -> None:
        path = Path(__file__).resolve().parents[1] / "app" / "core" / "gene_pack_seeds.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for pack in data["packs"]:
            for slug in pack["slugs"]:
                assert slug in ATOM_CATALOG, f"{slug} missing from ATOM_CATALOG"
