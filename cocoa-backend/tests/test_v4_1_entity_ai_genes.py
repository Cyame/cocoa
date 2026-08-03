"""v4.1 entity ai_genes aggregate + entity namespace mutation authz.

Covers the read-side ``ai_genes`` response field (explicit ``extra_added``
junction rows vs ``from_base_class`` inheritance via the preset BaseClass,
with explicit-source dedup) and the write-side requirement of the
``can_manage_namespace`` atom for entity PATCH / DELETE.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient


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


def _genes_by_slug(body: dict) -> dict[str, str]:
    genes = body.get("ai_genes") or []
    return {g["slug"]: g["source"] for g in genes}


class TestEntityAiGenesAggregate:
    @pytest.mark.asyncio
    async def test_inherited_gene_via_preset_base_class(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        admin_token, admin_id = _register(
            client,
            f"v41g-a-{uuid.uuid4().hex[:6]}",
            f"v41g-a-{uuid.uuid4().hex[:6]}@t.co",
        )
        bundle = await create_org_bundle(
            admin_id,
            atoms=(
                "can_manage_organization",
                "can_manage_ai_genes",
                "can_manage_namespace",
            ),
        )
        headers = {**_auth(admin_token), "X-Organization-Id": bundle.org.id}

        bc = client.post(
            "/api/v1/base-classes",
            headers=headers,
            json={
                "slug": f"v41g-bc-{uuid.uuid4().hex[:6]}",
                "name": "Gene Carrier",
            },
        )
        assert bc.status_code == 201, bc.text
        bc_id = bc.json()["id"]
        bc_slug = bc.json()["slug"]

        gene = client.post(
            "/api/v1/ai-genes",
            headers=headers,
            json={
                "slug": f"v41g-gene-{uuid.uuid4().hex[:6]}",
                "name": "Inherited Gene",
            },
        )
        assert gene.status_code == 201, gene.text
        gene_id = gene.json()["id"]
        gene_slug = gene.json()["slug"]

        linked = client.post(
            f"/api/v1/ai-genes/{gene_id}/attach-base-class",
            headers=headers,
            json={"base_class_id": bc_id},
        )
        assert linked.status_code == 201, linked.text

        ent = client.post(
            "/api/v1/entities",
            headers=_auth(admin_token),
            json={
                "slug": f"v41g-ent-{uuid.uuid4().hex[:6]}",
                "name": "Gene Entity",
                "rank": "intern",
                "preset_slug": bc_slug,
            },
        )
        assert ent.status_code == 201, ent.text
        entity_id = ent.json()["id"]
        assert _genes_by_slug(ent.json()) == {gene_slug: "from_base_class"}

        detail = client.get(
            f"/api/v1/entities/{entity_id}", headers=_auth(admin_token)
        )
        assert detail.status_code == 200
        assert _genes_by_slug(detail.json()) == {gene_slug: "from_base_class"}

    @pytest.mark.asyncio
    async def test_extra_added_attach_and_explicit_dedup(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        admin_token, admin_id = _register(
            client,
            f"v41g-b-{uuid.uuid4().hex[:6]}",
            f"v41g-b-{uuid.uuid4().hex[:6]}@t.co",
        )
        bundle = await create_org_bundle(
            admin_id,
            atoms=(
                "can_manage_organization",
                "can_manage_ai_genes",
                "can_manage_namespace",
            ),
        )
        headers = {**_auth(admin_token), "X-Organization-Id": bundle.org.id}

        bc = client.post(
            "/api/v1/base-classes",
            headers=headers,
            json={
                "slug": f"v41g-bc-{uuid.uuid4().hex[:6]}",
                "name": "Gene Carrier 2",
            },
        )
        assert bc.status_code == 201, bc.text
        bc_id = bc.json()["id"]
        bc_slug = bc.json()["slug"]

        gene_a = client.post(
            "/api/v1/ai-genes",
            headers=headers,
            json={
                "slug": f"v41g-gene-a-{uuid.uuid4().hex[:6]}",
                "name": "Inherited Gene",
            },
        )
        assert gene_a.status_code == 201, gene_a.text
        gene_a_id = gene_a.json()["id"]
        gene_a_slug = gene_a.json()["slug"]

        gene_b = client.post(
            "/api/v1/ai-genes",
            headers=headers,
            json={
                "slug": f"v41g-gene-b-{uuid.uuid4().hex[:6]}",
                "name": "Extra Gene",
            },
        )
        assert gene_b.status_code == 201, gene_b.text
        gene_b_id = gene_b.json()["id"]
        gene_b_slug = gene_b.json()["slug"]

        linked = client.post(
            f"/api/v1/ai-genes/{gene_a_id}/attach-base-class",
            headers=headers,
            json={"base_class_id": bc_id},
        )
        assert linked.status_code == 201, linked.text

        ent = client.post(
            "/api/v1/entities",
            headers=_auth(admin_token),
            json={
                "slug": f"v41g-ent-{uuid.uuid4().hex[:6]}",
                "name": "Gene Entity 2",
                "rank": "intern",
                "preset_slug": bc_slug,
            },
        )
        assert ent.status_code == 201, ent.text
        entity_id = ent.json()["id"]

        attached = client.post(
            f"/api/v1/entities/{entity_id}/ai-genes",
            headers=_auth(admin_token),
            json={"ai_gene_id": gene_b_id},
        )
        assert attached.status_code == 201, attached.text

        detail = client.get(
            f"/api/v1/entities/{entity_id}", headers=_auth(admin_token)
        )
        assert detail.status_code == 200
        assert _genes_by_slug(detail.json()) == {
            gene_a_slug: "from_base_class",
            gene_b_slug: "extra_added",
        }

        attached_a = client.post(
            f"/api/v1/entities/{entity_id}/ai-genes",
            headers=_auth(admin_token),
            json={"ai_gene_id": gene_a_id},
        )
        assert attached_a.status_code == 201, attached_a.text

        detail = client.get(
            f"/api/v1/entities/{entity_id}", headers=_auth(admin_token)
        )
        sources = _genes_by_slug(detail.json())
        assert sources[gene_a_slug] == "extra_added"
        assert sources[gene_b_slug] == "extra_added"
        assert len(sources) == 2

        listed = client.get("/api/v1/entities", headers=_auth(admin_token))
        assert listed.status_code == 200
        items = {item["id"]: item for item in listed.json()["items"]}
        assert _genes_by_slug(items[entity_id]) == {
            gene_a_slug: "extra_added",
            gene_b_slug: "extra_added",
        }

    @pytest.mark.asyncio
    async def test_member_delete_and_patch_forbidden_then_admin_succeeds(
        self,
        client: TestClient,
        session: AsyncSession,
        create_org_bundle,
    ) -> None:
        admin_token, admin_id = _register(
            client,
            f"v41g-c-{uuid.uuid4().hex[:6]}",
            f"v41g-c-{uuid.uuid4().hex[:6]}@t.co",
        )
        await create_org_bundle(admin_id, atoms=("can_manage_namespace",))
        member_token, _member_id = _register(
            client,
            f"v41g-m-{uuid.uuid4().hex[:6]}",
            f"v41g-m-{uuid.uuid4().hex[:6]}@t.co",
        )

        ent = client.post(
            "/api/v1/entities",
            headers=_auth(admin_token),
            json={
                "slug": f"v41g-del-{uuid.uuid4().hex[:6]}",
                "name": "Doomed Entity",
            },
        )
        assert ent.status_code == 201, ent.text
        entity_id = ent.json()["id"]

        forbidden_patch = client.patch(
            f"/api/v1/entities/{entity_id}",
            headers=_auth(member_token),
            json={"name": "Hijacked"},
        )
        assert forbidden_patch.status_code == 403
        assert forbidden_patch.json()["error_code"] == "permission.denied"

        forbidden_delete = client.delete(
            f"/api/v1/entities/{entity_id}",
            headers=_auth(member_token),
        )
        assert forbidden_delete.status_code == 403
        assert forbidden_delete.json()["error_code"] == "permission.denied"

        deleted = client.delete(
            f"/api/v1/entities/{entity_id}",
            headers=_auth(admin_token),
        )
        assert deleted.status_code == 204

        gone = client.get(
            f"/api/v1/entities/{entity_id}", headers=_auth(admin_token)
        )
        assert gone.status_code == 404
