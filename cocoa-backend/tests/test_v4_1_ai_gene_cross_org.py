"""v4.1 ai-gene ↔ base-class cross-org boundary tests.

The attach/detach endpoints validate the gene side (can_manage_ai_genes on
the gene's org) AND the base-class side (can_manage_ai_genes on the BC's org,
unless the BC is system-scoped). A user holding the atom only on the gene's
org must not write a junction touching a base class in another org.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models.ai_gene import AiGene, BaseClassAiGene
from app.models.base_class import BaseClass
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


def _create_org_gene(
    client: TestClient, token: str, org_id: str, slug: str
) -> str:
    """POST an org-scoped ai gene via API; return its id."""
    resp = client.post(
        "/api/v1/ai-genes",
        headers={**_auth(token), "X-Organization-Id": org_id},
        json={"slug": slug, "name": "Gene A", "scope": "org"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestAiGeneCrossOrgBoundary:
    @pytest.mark.asyncio
    async def test_attach_org_a_gene_to_org_b_base_class_forbidden(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        # First registered user is super-admin; the member must NOT be it,
        # otherwise the super-admin bypass would defeat the BC-side gate.
        _register(client, f"xorg-a-{uuid.uuid4().hex[:6]}", f"xorg-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"xorg-m-{uuid.uuid4().hex[:6]}", f"xorg-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle_a = await create_org_bundle(member_id, atoms=("can_manage_ai_genes",))
        org_b = Organization(slug=f"xorg-b-{uuid.uuid4().hex[:6]}", name="Org B")
        session.add(org_b)
        await session.flush()
        bc_b = BaseClass(
            slug=f"bc-b-{uuid.uuid4().hex[:8]}",
            name="BC B",
            scope="org",
            organization_id=org_b.id,
        )
        session.add(bc_b)
        await session.commit()

        gene_id = _create_org_gene(
            client,
            member_token,
            bundle_a.org.id,
            f"gene-a-{uuid.uuid4().hex[:8]}",
        )
        attach = client.post(
            f"/api/v1/ai-genes/{gene_id}/attach-base-class",
            headers={**_auth(member_token), "X-Organization-Id": bundle_a.org.id},
            json={"base_class_id": bc_b.id},
        )
        assert attach.status_code == 403, attach.text
        assert attach.json()["error_code"] == "permission.denied"

    @pytest.mark.asyncio
    async def test_attach_org_a_gene_to_system_base_class_allowed(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        _register(client, f"xorg-a-{uuid.uuid4().hex[:6]}", f"xorg-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"xorg-m-{uuid.uuid4().hex[:6]}", f"xorg-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle_a = await create_org_bundle(member_id, atoms=("can_manage_ai_genes",))
        sys_bc = BaseClass(
            slug=f"bc-sys-{uuid.uuid4().hex[:8]}",
            name="BC Sys",
            scope="system",
        )
        session.add(sys_bc)
        await session.commit()

        gene_id = _create_org_gene(
            client,
            member_token,
            bundle_a.org.id,
            f"gene-a-{uuid.uuid4().hex[:8]}",
        )
        attach = client.post(
            f"/api/v1/ai-genes/{gene_id}/attach-base-class",
            headers={**_auth(member_token), "X-Organization-Id": bundle_a.org.id},
            json={"base_class_id": sys_bc.id},
        )
        assert attach.status_code == 201, attach.text
        assert attach.json()["status"] == "attached"

    @pytest.mark.asyncio
    async def test_detach_org_a_gene_from_org_b_base_class_forbidden(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        _register(client, f"xorg-a-{uuid.uuid4().hex[:6]}", f"xorg-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"xorg-m-{uuid.uuid4().hex[:6]}", f"xorg-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle_a = await create_org_bundle(member_id, atoms=("can_manage_ai_genes",))
        org_b = Organization(slug=f"xorg-b-{uuid.uuid4().hex[:6]}", name="Org B")
        session.add(org_b)
        await session.flush()
        bc_b = BaseClass(
            slug=f"bc-b-{uuid.uuid4().hex[:8]}",
            name="BC B",
            scope="org",
            organization_id=org_b.id,
        )
        gene_a = AiGene(
            slug=f"gene-a-{uuid.uuid4().hex[:8]}",
            name="Gene A",
            scope="org",
            organization_id=bundle_a.org.id,
        )
        session.add_all([bc_b, gene_a])
        await session.flush()
        # Junction created out-of-band (super-admin write path / direct fixture).
        session.add(BaseClassAiGene(base_class_id=bc_b.id, ai_gene_id=gene_a.id))
        await session.commit()

        detach = client.delete(
            f"/api/v1/ai-genes/{gene_a.id}/attach-base-class/{bc_b.id}",
            headers={**_auth(member_token), "X-Organization-Id": bundle_a.org.id},
        )
        assert detach.status_code == 403, detach.text
        assert detach.json()["error_code"] == "permission.denied"

        # Junction must survive: the gate blocks before any soft-delete.
        link = (
            await session.execute(
                select(BaseClassAiGene).where(
                    BaseClassAiGene.base_class_id == bc_b.id,
                    BaseClassAiGene.ai_gene_id == gene_a.id,
                )
            )
        ).scalar_one()
        assert link.deleted_at is None
