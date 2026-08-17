"""v4-3 lane 4: merged namespace-contract list shape + atoms-only PATCH.

Coverage:
- Baseline: GET /namespaces/{nsId}/contracts shape — passed on the old
  (``user_id`` flat + ``genes`` [{id, slug}]) shape, now pins the merged
  default shape.
- New (v4-3 locked): ``?include_inherited=true`` returns ``contract_id`` +
  nested ``user`` + ``namespace_atoms`` + ``inherited_org_atoms``; default
  omits ``inherited_org_atoms`` entirely.
- Overlapping slugs appear in both atom lists (ns + inherited org).
- ``PATCH .../contracts/{id}/atoms`` writes ONLY ``namespace_contract_genes``
  (slugs or gene_ids), never the org layer.
- Existing POST / PATCH / DELETE routes keep working.
- Adversarial: malformed ``include_inherited`` → 422; non-member → 403.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from starlette.testclient import TestClient

from app.models.user_gene import UserGene


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(
    client: TestClient, username: str, email: str
) -> tuple[str, str]:
    """Register; returns (token, user_id).

    The first registered user in a fresh test DB auto-promotes to
    super-admin; subsequent registrations are non-super-admin.
    """
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


async def _gene_id(session, slug: str) -> str:
    gene = (
        await session.execute(
            select(UserGene).where(
                UserGene.slug == slug,
                UserGene.deleted_at.is_(None),
            )
        )
    ).scalar_one()
    return gene.id


class TestBaselineCurrentShape:
    """Characterization: GET response shape, pre- and post-v4-3.

    Passed on the unchanged code (flat ``user_id`` + ``genes`` [{id, slug}]);
    the v4-3 API intentionally breaks that shape, so this test now pins the
    merged default (no ``include_inherited``) shape instead.
    """

    @pytest.mark.asyncio
    async def test_list_contracts_default_shape(
        self, client: TestClient, session, namespace_factory
    ) -> None:
        token, user_id = _register(
            client, f"v43-base-{uuid.uuid4().hex[:6]}", f"v43-base-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"v43-base-ns-{uuid.uuid4().hex[:6]}")
        await session.commit()

        created = client.post(
            f"/api/v1/namespaces/{ns.id}/contracts",
            headers=_auth(token),
            json={"user_id": user_id, "gene_slugs": ["can_view_workspace"]},
        )
        assert created.status_code == 201, created.text
        assert created.json()["genes"][0]["slug"] == "can_view_workspace"

        resp = client.get(
            f"/api/v1/namespaces/{ns.id}/contracts", headers=_auth(token)
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert body["total"] >= 1
        item = next(c for c in body["items"] if c["user"]["id"] == user_id)
        assert item["contract_id"] == created.json()["id"]
        assert {a["slug"] for a in item["namespace_atoms"]} == {
            "can_view_workspace"
        }
        assert "inherited_org_atoms" not in item
        assert item["user"]["username"]
        assert item["user"]["email"]
        assert "created_at" in item


class TestMergedListShape:
    @pytest.mark.asyncio
    async def test_include_inherited_true_returns_merged_items(
        self,
        client: TestClient,
        session,
        namespace_factory,
        create_org_bundle,
    ) -> None:
        token, user_id = _register(
            client, f"v43-merg-{uuid.uuid4().hex[:6]}", f"v43-merg-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"v43-merg-ns-{uuid.uuid4().hex[:6]}")
        await create_org_bundle(
            user_id,
            atoms=("can_manage_organization", "can_view_workspace"),
            namespace=ns,
        )

        created = client.post(
            f"/api/v1/namespaces/{ns.id}/contracts",
            headers=_auth(token),
            json={"user_id": user_id, "gene_slugs": ["can_edit_workspace"]},
        )
        assert created.status_code == 201, created.text

        resp = client.get(
            f"/api/v1/namespaces/{ns.id}/contracts?include_inherited=true",
            headers=_auth(token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["limit"] == 50 and body["offset"] == 0 and body["total"] >= 1
        item = next(c for c in body["items"] if c["user"]["id"] == user_id)

        # Locked shape keys (B3+H6): contract_id, nested user, two atom lists.
        assert item["contract_id"] == created.json()["id"]
        assert item["user"]["id"] == user_id
        assert item["user"]["nickname"] is None
        assert item["user"]["username"]
        assert item["user"]["email"]
        assert "created_at" in item

        ns_slugs = {a["slug"] for a in item["namespace_atoms"]}
        org_slugs = {a["slug"] for a in item["inherited_org_atoms"]}
        assert ns_slugs == {"can_edit_workspace"}
        assert {"can_manage_organization", "can_view_workspace"} <= org_slugs
        # Atom entries carry id/slug/name (name from UserGene.name).
        assert all({"id", "slug", "name"} <= set(a) for a in item["namespace_atoms"])
        assert all({"id", "slug", "name"} <= set(a) for a in item["inherited_org_atoms"])

    @pytest.mark.asyncio
    async def test_include_inherited_false_omits_inherited_key(
        self, client: TestClient, session, namespace_factory, create_org_bundle
    ) -> None:
        token, user_id = _register(
            client, f"v43-omit-{uuid.uuid4().hex[:6]}", f"v43-omit-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"v43-omit-ns-{uuid.uuid4().hex[:6]}")
        await create_org_bundle(
            user_id, atoms=("can_manage_organization",), namespace=ns
        )
        created = client.post(
            f"/api/v1/namespaces/{ns.id}/contracts",
            headers=_auth(token),
            json={"user_id": user_id, "gene_slugs": ["can_edit_workspace"]},
        )
        assert created.status_code == 201, created.text

        # Default (no query param) must ALSO be the merged shape.
        resp = client.get(
            f"/api/v1/namespaces/{ns.id}/contracts", headers=_auth(token)
        )
        assert resp.status_code == 200, resp.text
        item = next(
            c for c in resp.json()["items"] if c["user"]["id"] == user_id
        )
        assert item["contract_id"] == created.json()["id"]
        assert "inherited_org_atoms" not in item
        assert {a["slug"] for a in item["namespace_atoms"]} == {
            "can_edit_workspace"
        }
        # Explicit false behaves identically.
        resp2 = client.get(
            f"/api/v1/namespaces/{ns.id}/contracts?include_inherited=false",
            headers=_auth(token),
        )
        assert resp2.status_code == 200, resp2.text
        item2 = next(
            c for c in resp2.json()["items"] if c["user"]["id"] == user_id
        )
        assert "inherited_org_atoms" not in item2

    @pytest.mark.asyncio
    async def test_overlapping_slug_appears_in_both_lists(
        self, client: TestClient, session, namespace_factory, create_org_bundle
    ) -> None:
        token, user_id = _register(
            client, f"v43-over-{uuid.uuid4().hex[:6]}", f"v43-over-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"v43-over-ns-{uuid.uuid4().hex[:6]}")
        await create_org_bundle(
            user_id,
            atoms=("can_manage_organization", "can_edit_workspace"),
            namespace=ns,
        )
        created = client.post(
            f"/api/v1/namespaces/{ns.id}/contracts",
            headers=_auth(token),
            json={"user_id": user_id, "gene_slugs": ["can_edit_workspace"]},
        )
        assert created.status_code == 201, created.text

        resp = client.get(
            f"/api/v1/namespaces/{ns.id}/contracts?include_inherited=true",
            headers=_auth(token),
        )
        assert resp.status_code == 200, resp.text
        item = next(
            c for c in resp.json()["items"] if c["user"]["id"] == user_id
        )
        ns_slugs = {a["slug"] for a in item["namespace_atoms"]}
        org_slugs = {a["slug"] for a in item["inherited_org_atoms"]}
        assert "can_edit_workspace" in ns_slugs
        assert "can_edit_workspace" in org_slugs
        assert "can_manage_organization" in org_slugs


class TestAtomsPatch:
    @pytest.mark.asyncio
    async def test_patch_atoms_writes_only_namespace_genes(
        self, client: TestClient, session, namespace_factory, create_org_bundle
    ) -> None:
        token, user_id = _register(
            client, f"v43-atom-{uuid.uuid4().hex[:6]}", f"v43-atom-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"v43-atom-ns-{uuid.uuid4().hex[:6]}")
        await create_org_bundle(
            user_id,
            atoms=("can_view_workspace", "can_edit_workspace"),
            namespace=ns,
        )
        created = client.post(
            f"/api/v1/namespaces/{ns.id}/contracts",
            headers=_auth(token),
            json={"user_id": user_id, "gene_slugs": ["can_view_workspace"]},
        )
        assert created.status_code == 201, created.text
        contract_id = created.json()["id"]

        patched = client.patch(
            f"/api/v1/namespaces/{ns.id}/contracts/{contract_id}/atoms",
            headers=_auth(token),
            json={"atom_slugs": ["can_manage_workspace"]},
        )
        assert patched.status_code == 200, patched.text

        resp = client.get(
            f"/api/v1/namespaces/{ns.id}/contracts?include_inherited=true",
            headers=_auth(token),
        )
        assert resp.status_code == 200, resp.text
        item = next(
            c for c in resp.json()["items"] if c["user"]["id"] == user_id
        )
        assert {a["slug"] for a in item["namespace_atoms"]} == {
            "can_manage_workspace"
        }
        # Org layer untouched: can_view_workspace / can_edit_workspace remain.
        org_slugs = {a["slug"] for a in item["inherited_org_atoms"]}
        assert {"can_view_workspace", "can_edit_workspace"} <= org_slugs

    @pytest.mark.asyncio
    async def test_patch_atoms_by_gene_ids(
        self, client: TestClient, session, namespace_factory, create_org_bundle
    ) -> None:
        token, user_id = _register(
            client, f"v43-gids-{uuid.uuid4().hex[:6]}", f"v43-gids-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"v43-gids-ns-{uuid.uuid4().hex[:6]}")
        await create_org_bundle(
            user_id, atoms=("can_view_workspace",), namespace=ns
        )
        created = client.post(
            f"/api/v1/namespaces/{ns.id}/contracts",
            headers=_auth(token),
            json={"user_id": user_id, "gene_slugs": ["can_view_workspace"]},
        )
        assert created.status_code == 201, created.text
        contract_id = created.json()["id"]

        operate_gene_id = await _gene_id(session, "can_operate_workspace")
        patched = client.patch(
            f"/api/v1/namespaces/{ns.id}/contracts/{contract_id}/atoms",
            headers=_auth(token),
            json={"gene_ids": [operate_gene_id]},
        )
        assert patched.status_code == 200, patched.text
        assert {
            a["slug"] for a in patched.json()["namespace_atoms"]
        } == {"can_operate_workspace"}
        assert "inherited_org_atoms" not in patched.json()

    @pytest.mark.asyncio
    async def test_patch_atoms_rejects_both_or_neither(
        self, client: TestClient, session, namespace_factory
    ) -> None:
        token, user_id = _register(
            client, f"v43-both-{uuid.uuid4().hex[:6]}", f"v43-both-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"v43-both-ns-{uuid.uuid4().hex[:6]}")
        await session.commit()
        created = client.post(
            f"/api/v1/namespaces/{ns.id}/contracts",
            headers=_auth(token),
            json={"user_id": user_id, "gene_slugs": ["can_view_workspace"]},
        )
        assert created.status_code == 201, created.text
        contract_id = created.json()["id"]
        url = f"/api/v1/namespaces/{ns.id}/contracts/{contract_id}/atoms"

        both = client.patch(
            url,
            headers=_auth(token),
            json={"atom_slugs": ["can_view_workspace"], "gene_ids": ["x"]},
        )
        assert both.status_code == 422
        assert both.json()["error_code"] == "namespace_contract.atoms_conflict"

        neither = client.patch(url, headers=_auth(token), json={})
        assert neither.status_code == 422
        assert neither.json()["error_code"] == "namespace_contract.atoms_required"

        unknown = client.patch(
            url,
            headers=_auth(token),
            json={"gene_ids": ["no-such-gene-id"]},
        )
        assert unknown.status_code == 404
        assert unknown.json()["error_code"] == "user_gene.not_found"


class TestExistingCrudStillWorks:
    @pytest.mark.asyncio
    async def test_post_patch_delete_contracts(
        self, client: TestClient, session, namespace_factory
    ) -> None:
        token, user_id = _register(
            client, f"v43-crud-{uuid.uuid4().hex[:6]}", f"v43-crud-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"v43-crud-ns-{uuid.uuid4().hex[:6]}")
        await session.commit()

        created = client.post(
            f"/api/v1/namespaces/{ns.id}/contracts",
            headers=_auth(token),
            json={"user_id": user_id, "gene_slugs": ["can_view_workspace"]},
        )
        assert created.status_code == 201, created.text
        contract_id = created.json()["id"]
        assert created.json()["id"]

        updated = client.patch(
            f"/api/v1/namespaces/{ns.id}/contracts/{contract_id}",
            headers=_auth(token),
            json={"gene_slugs": ["can_view_workspace", "can_edit_workspace"]},
        )
        assert updated.status_code == 200, updated.text
        assert {g["slug"] for g in updated.json()["genes"]} == {
            "can_view_workspace",
            "can_edit_workspace",
        }

        deleted = client.delete(
            f"/api/v1/namespaces/{ns.id}/contracts/{contract_id}",
            headers=_auth(token),
        )
        assert deleted.status_code == 204, deleted.text

        resp = client.get(
            f"/api/v1/namespaces/{ns.id}/contracts?include_inherited=true",
            headers=_auth(token),
        )
        assert resp.status_code == 200, resp.text
        assert all(
            c["contract_id"] != contract_id for c in resp.json()["items"]
        )


class TestAdversarial:
    @pytest.mark.asyncio
    async def test_malformed_include_inherited_rejected(
        self, client: TestClient, session, namespace_factory
    ) -> None:
        token, _ = _register(
            client, f"v43-bad-{uuid.uuid4().hex[:6]}", f"v43-bad-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"v43-bad-ns-{uuid.uuid4().hex[:6]}")
        await session.commit()

        resp = client.get(
            f"/api/v1/namespaces/{ns.id}/contracts?include_inherited=notabool",
            headers=_auth(token),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_non_member_cannot_list_contracts(
        self, client: TestClient, session, namespace_factory
    ) -> None:
        _register(
            client, f"v43-adm-{uuid.uuid4().hex[:6]}", f"v43-adm-{uuid.uuid4().hex[:6]}@t.co"
        )
        member_token, _ = _register(
            client, f"v43-mem-{uuid.uuid4().hex[:6]}", f"v43-mem-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"v43-mem-ns-{uuid.uuid4().hex[:6]}")
        await session.commit()

        resp = client.get(
            f"/api/v1/namespaces/{ns.id}/contracts?include_inherited=true",
            headers=_auth(member_token),
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"
