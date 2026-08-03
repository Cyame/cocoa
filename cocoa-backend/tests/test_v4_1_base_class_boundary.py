"""v4.1 cross-org boundary gates on BaseClass attach/detach + update/delete.

Covers two gaps closed against `ai_genes.py`'s org-boundary pattern:

1. The four attach/detach endpoints on BaseClass validate the capability /
   ai-gene side too — a user holding ``can_manage_capabilities`` /
   ``can_manage_ai_genes`` on the BaseClass's org can no longer reference a
   capability / gene that belongs to ANOTHER org (403).
   System-scoped capabilities / genes stay attachable by anyone with
   BaseClass-side permission (201).
2. ``update_base_class`` / ``delete_base_class`` reject an org-scoped
   BaseClass owned by a different org than the caller's active context with a
   **404** (anti-enumeration, same shape as ai_genes.py).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models.ai_gene import AiGene
from app.models.base_class import BaseClass
from app.models.capability_market import CapabilityMarketEntry
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


def _uid() -> str:
    return uuid.uuid4().hex[:6]


async def _create_org_b_scoped_base_class(
    session: AsyncSession, org_b: Organization
) -> BaseClass:
    bc = BaseClass(
        slug=f"bc-b-{_uid()}",
        name="Org B BaseClass",
        scope="org",
        organization_id=org_b.id,
    )
    session.add(bc)
    await session.flush()
    return bc


class TestCrossOrgCapabilityAttach:
    @pytest.mark.asyncio
    async def test_attach_org_b_capability_to_org_a_base_class_forbidden(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        """Org A manager must not attach an org-B capability (cross-org leak)."""
        _register(client, f"bnd-a-{_uid()}", f"bnd-a-{_uid()}@t.co")
        token, member_id = _register(
            client, f"bnd-m-{_uid()}", f"bnd-m-{_uid()}@t.co"
        )
        bundle = await create_org_bundle(
            member_id,
            atoms=("can_manage_organization", "can_manage_capabilities"),
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        bc = client.post(
            "/api/v1/base-classes",
            headers=headers,
            json={"slug": f"bc-a-{_uid()}", "name": "Org A BaseClass"},
        )
        assert bc.status_code == 201, bc.text
        bc_id = bc.json()["id"]

        org_b = Organization(slug=f"org-b-{_uid()}", name="Org B")
        session.add(org_b)
        await session.flush()
        cap_b = CapabilityMarketEntry(
            name=f"cap-b-{_uid()}",
            type="skill",
            scope="org",
            organization_id=org_b.id,
            created_via="manual",
        )
        session.add(cap_b)
        await session.commit()

        attach = client.post(
            f"/api/v1/base-classes/{bc_id}/capabilities",
            headers=headers,
            json={"capability_id": cap_b.id},
        )
        assert attach.status_code == 403
        assert "error_code" in attach.json()
        assert attach.json()["error_code"] == "permission.denied"

    @pytest.mark.asyncio
    async def test_attach_system_capability_to_org_a_base_class_allowed(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        """System-scoped capabilities are attachable by any BC-side manager."""
        _register(client, f"bnd-a-{_uid()}", f"bnd-a-{_uid()}@t.co")
        token, member_id = _register(
            client, f"bnd-m-{_uid()}", f"bnd-m-{_uid()}@t.co"
        )
        bundle = await create_org_bundle(
            member_id,
            atoms=("can_manage_organization", "can_manage_capabilities"),
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        bc = client.post(
            "/api/v1/base-classes",
            headers=headers,
            json={"slug": f"bc-a-{_uid()}", "name": "Org A BaseClass"},
        )
        assert bc.status_code == 201, bc.text
        bc_id = bc.json()["id"]

        sys_cap = CapabilityMarketEntry(
            name=f"sys-cap-{_uid()}",
            type="skill",
            scope="system",
            created_via="manual",
        )
        session.add(sys_cap)
        await session.commit()

        attach = client.post(
            f"/api/v1/base-classes/{bc_id}/capabilities",
            headers=headers,
            json={"capability_id": sys_cap.id},
        )
        assert attach.status_code == 201, attach.text

        detach = client.delete(
            f"/api/v1/base-classes/{bc_id}/capabilities/{sys_cap.id}",
            headers=headers,
        )
        assert detach.status_code == 204

    @pytest.mark.asyncio
    async def test_detach_org_b_capability_from_org_a_base_class_forbidden(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        """Org A manager must not detach an org-B capability either."""
        _register(client, f"bnd-a-{_uid()}", f"bnd-a-{_uid()}@t.co")
        token, member_id = _register(
            client, f"bnd-m-{_uid()}", f"bnd-m-{_uid()}@t.co"
        )
        bundle = await create_org_bundle(
            member_id,
            atoms=("can_manage_organization", "can_manage_capabilities"),
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        bc = client.post(
            "/api/v1/base-classes",
            headers=headers,
            json={"slug": f"bc-a-{_uid()}", "name": "Org A BaseClass"},
        )
        assert bc.status_code == 201, bc.text
        bc_id = bc.json()["id"]

        org_b = Organization(slug=f"org-b-{_uid()}", name="Org B")
        session.add(org_b)
        await session.flush()
        cap_b = CapabilityMarketEntry(
            name=f"cap-b-{_uid()}",
            type="skill",
            scope="org",
            organization_id=org_b.id,
            created_via="manual",
        )
        session.add(cap_b)
        await session.commit()

        detach = client.delete(
            f"/api/v1/base-classes/{bc_id}/capabilities/{cap_b.id}",
            headers=headers,
        )
        assert detach.status_code == 403
        assert "error_code" in detach.json()
        assert detach.json()["error_code"] == "permission.denied"


class TestCrossOrgAiGeneAttach:
    @pytest.mark.asyncio
    async def test_attach_org_b_ai_gene_to_org_a_base_class_forbidden(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        """Org A manager must not attach an org-B ai-gene (cross-org leak)."""
        _register(client, f"bnd-a-{_uid()}", f"bnd-a-{_uid()}@t.co")
        token, member_id = _register(
            client, f"bnd-m-{_uid()}", f"bnd-m-{_uid()}@t.co"
        )
        bundle = await create_org_bundle(
            member_id,
            atoms=("can_manage_organization", "can_manage_ai_genes"),
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        bc = client.post(
            "/api/v1/base-classes",
            headers=headers,
            json={"slug": f"bc-a-{_uid()}", "name": "Org A BaseClass"},
        )
        assert bc.status_code == 201, bc.text
        bc_id = bc.json()["id"]

        org_b = Organization(slug=f"org-b-{_uid()}", name="Org B")
        session.add(org_b)
        await session.flush()
        gene_b = AiGene(
            slug=f"gene-b-{_uid()}",
            name="Org B Gene",
            scope="org",
            organization_id=org_b.id,
        )
        session.add(gene_b)
        await session.commit()

        attach = client.post(
            f"/api/v1/base-classes/{bc_id}/ai-genes",
            headers=headers,
            json={"ai_gene_id": gene_b.id},
        )
        assert attach.status_code == 403
        assert "error_code" in attach.json()
        assert attach.json()["error_code"] == "permission.denied"

    @pytest.mark.asyncio
    async def test_attach_system_ai_gene_to_org_a_base_class_allowed(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        """System-scoped ai-genes are attachable by any BC-side manager."""
        _register(client, f"bnd-a-{_uid()}", f"bnd-a-{_uid()}@t.co")
        token, member_id = _register(
            client, f"bnd-m-{_uid()}", f"bnd-m-{_uid()}@t.co"
        )
        bundle = await create_org_bundle(
            member_id,
            atoms=("can_manage_organization", "can_manage_ai_genes"),
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        bc = client.post(
            "/api/v1/base-classes",
            headers=headers,
            json={"slug": f"bc-a-{_uid()}", "name": "Org A BaseClass"},
        )
        assert bc.status_code == 201, bc.text
        bc_id = bc.json()["id"]

        sys_gene = AiGene(
            slug=f"sys-gene-{_uid()}",
            name="System Gene",
            scope="system",
        )
        session.add(sys_gene)
        await session.commit()

        attach = client.post(
            f"/api/v1/base-classes/{bc_id}/ai-genes",
            headers=headers,
            json={"ai_gene_id": sys_gene.id},
        )
        assert attach.status_code == 201, attach.text

        detach = client.delete(
            f"/api/v1/base-classes/{bc_id}/ai-genes/{sys_gene.id}",
            headers=headers,
        )
        assert detach.status_code == 204

    @pytest.mark.asyncio
    async def test_detach_org_b_ai_gene_from_org_a_base_class_forbidden(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        """Org A manager must not detach an org-B ai-gene either."""
        _register(client, f"bnd-a-{_uid()}", f"bnd-a-{_uid()}@t.co")
        token, member_id = _register(
            client, f"bnd-m-{_uid()}", f"bnd-m-{_uid()}@t.co"
        )
        bundle = await create_org_bundle(
            member_id,
            atoms=("can_manage_organization", "can_manage_ai_genes"),
        )
        headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

        bc = client.post(
            "/api/v1/base-classes",
            headers=headers,
            json={"slug": f"bc-a-{_uid()}", "name": "Org A BaseClass"},
        )
        assert bc.status_code == 201, bc.text
        bc_id = bc.json()["id"]

        org_b = Organization(slug=f"org-b-{_uid()}", name="Org B")
        session.add(org_b)
        await session.flush()
        gene_b = AiGene(
            slug=f"gene-b-{_uid()}",
            name="Org B Gene",
            scope="org",
            organization_id=org_b.id,
        )
        session.add(gene_b)
        await session.commit()

        detach = client.delete(
            f"/api/v1/base-classes/{bc_id}/ai-genes/{gene_b.id}",
            headers=headers,
        )
        assert detach.status_code == 403
        assert "error_code" in detach.json()
        assert detach.json()["error_code"] == "permission.denied"


class TestBaseClassUpdateDeleteBoundary:
    @pytest.mark.asyncio
    async def test_update_org_b_base_class_from_org_a_context_returns_404(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        """PATCH on an org-B BC while operating in org-A context → 404
        (anti-enumeration, same shape as ai_genes.py)."""
        _register(client, f"bnd-a-{_uid()}", f"bnd-a-{_uid()}@t.co")
        token, member_id = _register(
            client, f"bnd-m-{_uid()}", f"bnd-m-{_uid()}@t.co"
        )
        # User holds can_manage_organization on BOTH orgs; active context is A.
        bundle_a = await create_org_bundle(
            member_id, atoms=("can_manage_organization",)
        )
        org_b = Organization(slug=f"org-b-{_uid()}", name="Org B")
        session.add(org_b)
        await session.flush()
        await create_org_bundle(
            member_id,
            atoms=("can_manage_organization",),
            organization=org_b,
        )
        bc_b = await _create_org_b_scoped_base_class(session, org_b)
        await session.commit()

        headers = {**_auth(token), "X-Organization-Id": bundle_a.org.id}
        patch = client.patch(
            f"/api/v1/base-classes/{bc_b.id}",
            headers=headers,
            json={"description": "cross-org edit"},
        )
        assert patch.status_code == 404
        assert patch.json()["error_code"] == "base_class.not_found"

    @pytest.mark.asyncio
    async def test_delete_org_b_base_class_from_org_a_context_returns_404(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        """DELETE on an org-B BC while operating in org-A context → 404."""
        _register(client, f"bnd-a-{_uid()}", f"bnd-a-{_uid()}@t.co")
        token, member_id = _register(
            client, f"bnd-m-{_uid()}", f"bnd-m-{_uid()}@t.co"
        )
        bundle_a = await create_org_bundle(
            member_id, atoms=("can_manage_organization",)
        )
        org_b = Organization(slug=f"org-b-{_uid()}", name="Org B")
        session.add(org_b)
        await session.flush()
        await create_org_bundle(
            member_id,
            atoms=("can_manage_organization",),
            organization=org_b,
        )
        bc_b = await _create_org_b_scoped_base_class(session, org_b)
        await session.commit()

        headers = {**_auth(token), "X-Organization-Id": bundle_a.org.id}
        delete = client.delete(
            f"/api/v1/base-classes/{bc_b.id}",
            headers=headers,
        )
        assert delete.status_code == 404
        assert delete.json()["error_code"] == "base_class.not_found"
