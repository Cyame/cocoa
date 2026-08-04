"""v4-3 backend lane 3: world members (世界契印) API + cannot_lock_self (H5).

Covers:
- Baseline pin: GET /organizations/{id} (unchanged lane-1 CRUD behavior).
- GET  /organizations/{id}/members — OffsetPage of OrganizationContracts
  with a NESTED user {id, username, email, nickname} (never a UUID wall)
  and atoms [{id, slug, name}].
- POST /organizations/{id}/members — by user_id or unique-prefix q;
  atom_slugs validated against ATOM_CATALOG; duplicates → 409.
- PATCH /organizations/{id}/members/{contract_id} — full gene-set replace
  (removed genes soft-deleted); cannot_lock_self on self-strip (400).
- DELETE /organizations/{id}/members/{contract_id} — soft-deletes the
  contract + genes; cannot_lock_self when the org holds a single contract
  (org 仅一人) and the target is the caller.
- Super-admin bypasses both guards; non-members get 404; viewers get 403
  on CUD and on GET without view/manage atoms.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models.organization_contract import OrganizationContractGene
from app.models.user_gene import UserGene


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, username: str, email: str) -> tuple[str, str]:
    """Register; returns (token, user_id).

    The first registered user in a fresh test DB auto-promotes to
    super-admin; subsequent registrations are non-super-admin.
    """
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": "password123"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["id"]


def _create_org(client: TestClient, token: str, slug: str, name: str) -> dict:
    resp = client.post(
        "/api/v1/organizations",
        headers=_auth(token),
        json={"slug": slug, "name": name},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


async def _world(client: TestClient) -> dict:
    """Super-admin + a non-SA org owner (full ORG_OWNER_ATOMS contract)."""
    sa_token, _ = _register(
        client,
        f"om-sa-{uuid.uuid4().hex[:6]}",
        f"sa-{uuid.uuid4().hex[:6]}@t.co",
    )
    owner_token, owner_id = _register(
        client,
        f"om-own-{uuid.uuid4().hex[:6]}",
        f"own-{uuid.uuid4().hex[:6]}@t.co",
    )
    org = _create_org(
        client, owner_token, f"om-{uuid.uuid4().hex[:6]}", "Members World"
    )
    return {
        "sa_token": sa_token,
        "owner_token": owner_token,
        "owner_id": owner_id,
        "org": org,
    }


def _post_member(
    client: TestClient, env: dict, user_id: str, atom_slugs: list[str]
) -> dict:
    resp = client.post(
        f"/api/v1/organizations/{env['org']['id']}/members",
        headers=_auth(env["owner_token"]),
        json={"user_id": user_id, "atom_slugs": atom_slugs},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _fresh_gene_rows(
    db_url: str, contract_id: str
) -> tuple[list[UserGene], list[OrganizationContractGene]]:
    """Read active + deleted gene links through a fresh connection."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as s:
            active = (
                await s.execute(
                    select(UserGene)
                    .join(
                        OrganizationContractGene,
                        OrganizationContractGene.user_gene_id == UserGene.id,
                    )
                    .where(
                        OrganizationContractGene.contract_id == contract_id,
                        OrganizationContractGene.deleted_at.is_(None),
                        UserGene.deleted_at.is_(None),
                    )
                    .order_by(UserGene.slug)
                )
            ).scalars().all()
            gone = (
                await s.execute(
                    select(OrganizationContractGene).where(
                        OrganizationContractGene.contract_id == contract_id,
                        OrganizationContractGene.deleted_at.is_not(None),
                    )
                )
            ).scalars().all()
            return list(active), list(gone)
    finally:
        await engine.dispose()


class TestBaselineOrgGet:
    """Pin the unchanged lane-1 behavior of GET /organizations/{id}."""

    def test_member_can_get(self, client: TestClient) -> None:
        _register(client, "om-bl-sa", "om-bl-sa@t.co")
        owner_token, _ = _register(client, "om-bl-own", "om-bl-own@t.co")
        org = _create_org(client, owner_token, f"bl-{uuid.uuid4().hex[:6]}", "BL")
        resp = client.get(f"/api/v1/organizations/{org['id']}", headers=_auth(owner_token))
        assert resp.status_code == 200
        assert resp.json()["id"] == org["id"]

    def test_unknown_org_404(self, client: TestClient) -> None:
        _register(client, "om-bl-sa2", "om-bl-sa2@t.co")
        owner_token, _ = _register(client, "om-bl-own2", "om-bl-own2@t.co")
        resp = client.get(
            f"/api/v1/organizations/{uuid.uuid4()}", headers=_auth(owner_token)
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "organization.not_found"


class TestListMembers:
    async def test_nested_user_and_atoms(self, client: TestClient) -> None:
        env = await _world(client)
        username = f"om-tgt-{uuid.uuid4().hex[:6]}"
        _target_token, target_id = _register(client, username, f"{username}@t.co")
        created = _post_member(
            client, env, target_id, ["can_view_workspace", "can_edit_workspace"]
        )

        resp = client.get(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 2  # owner + target
        assert body["limit"] == 50
        assert body["offset"] == 0

        item = next(i for i in body["items"] if i["id"] == created["id"])
        # Real nested user — not a UUID wall.
        user = item["user"]
        assert isinstance(user, dict)
        assert user["id"] == target_id
        assert user["username"] == username
        assert user["email"] == f"{username}@t.co"
        assert user["nickname"] is None
        # Atoms carry slug + name.
        slugs = {a["slug"] for a in item["atoms"]}
        assert "can_view_workspace" in slugs
        assert "can_edit_workspace" in slugs
        atom = next(a for a in item["atoms"] if a["slug"] == "can_view_workspace")
        assert atom["id"]
        assert atom["name"]

    async def test_owner_item_has_full_atoms(self, client: TestClient) -> None:
        env = await _world(client)
        resp = client.get(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 1
        owner_item = items[0]
        assert owner_item["user"]["id"] == env["owner_id"]
        assert "can_manage_org_members" in {a["slug"] for a in owner_item["atoms"]}

    async def test_viewer_with_view_atom_can_list(self, client: TestClient) -> None:
        env = await _world(client)
        _target_token, target_id = _register(
            client, f"om-vw-{uuid.uuid4().hex[:6]}", f"vw-{uuid.uuid4().hex[:6]}@t.co"
        )
        _post_member(client, env, target_id, ["can_view_workspace"])
        resp = client.get(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(_target_token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] == 2

    async def test_member_without_view_or_manage_atom_forbidden(
        self, client: TestClient
    ) -> None:
        env = await _world(client)
        _target_token, target_id = _register(
            client, f"om-ed-{uuid.uuid4().hex[:6]}", f"ed-{uuid.uuid4().hex[:6]}@t.co"
        )
        _post_member(client, env, target_id, ["can_edit_workspace"])
        resp = client.get(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(_target_token),
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

    def test_non_member_gets_404(self, client: TestClient) -> None:
        _register(client, "om-nm-sa", "om-nm-sa@t.co")
        owner_token, _ = _register(client, "om-nm-own", "om-nm-own@t.co")
        org = _create_org(client, owner_token, f"nm-{uuid.uuid4().hex[:6]}", "NM")
        outsider_token, _ = _register(client, "om-nm-out", "om-nm-out@t.co")

        resp = client.get(
            f"/api/v1/organizations/{org['id']}/members",
            headers=_auth(outsider_token),
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "organization.not_found"

    def test_unknown_org_404(self, client: TestClient) -> None:
        _register(client, "om-uo-sa", "om-uo-sa@t.co")
        owner_token, _ = _register(client, "om-uo-own", "om-uo-own@t.co")
        resp = client.get(
            f"/api/v1/organizations/{uuid.uuid4()}/members",
            headers=_auth(owner_token),
        )
        assert resp.status_code == 404


class TestPostMember:
    async def test_post_by_user_id(self, client: TestClient) -> None:
        env = await _world(client)
        username = f"om-p1-{uuid.uuid4().hex[:6]}"
        _token, target_id = _register(client, username, f"{username}@t.co")

        resp = client.post(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
            json={"user_id": target_id, "atom_slugs": ["can_view_workspace"]},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["id"]
        assert body["user"]["username"] == username
        assert body["user"]["id"] == target_id
        assert [a["slug"] for a in body["atoms"]] == ["can_view_workspace"]
        assert body["atoms"][0]["name"]

    async def test_post_by_unique_q(self, client: TestClient) -> None:
        env = await _world(client)
        username = f"om-unique-{uuid.uuid4().hex[:6]}"
        _token, target_id = _register(client, username, f"{username}@t.co")

        resp = client.post(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
            json={"q": username[:12], "atom_slugs": ["can_view_workspace"]},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["user"]["id"] == target_id

    async def test_post_q_ambiguous_422(self, client: TestClient) -> None:
        env = await _world(client)
        for i in range(2):
            _register(client, f"share-{i}", f"share-{i}@t.co")
        resp = client.post(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
            json={"q": "share-", "atom_slugs": ["can_view_workspace"]},
        )
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "organization.member_ambiguous"

    async def test_post_q_no_match_404(self, client: TestClient) -> None:
        env = await _world(client)
        resp = client.post(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
            json={"q": "no-such-user-xyz", "atom_slugs": ["can_view_workspace"]},
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "user.not_found"

    async def test_post_unknown_user_id_404(self, client: TestClient) -> None:
        env = await _world(client)
        resp = client.post(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
            json={"user_id": str(uuid.uuid4()), "atom_slugs": ["can_view_workspace"]},
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "user.not_found"

    async def test_post_missing_target_422(self, client: TestClient) -> None:
        env = await _world(client)
        resp = client.post(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
            json={"atom_slugs": ["can_view_workspace"]},
        )
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "validation_error"

    async def test_post_both_user_id_and_q_422(self, client: TestClient) -> None:
        env = await _world(client)
        username = f"om-both-{uuid.uuid4().hex[:6]}"
        _token, target_id = _register(client, username, f"{username}@t.co")
        resp = client.post(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
            json={"user_id": target_id, "q": username, "atom_slugs": []},
        )
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "validation_error"

    async def test_post_invalid_atom_slug_422(self, client: TestClient) -> None:
        env = await _world(client)
        _token, target_id = _register(
            client, f"om-bad-{uuid.uuid4().hex[:6]}", f"bad-{uuid.uuid4().hex[:6]}@t.co"
        )
        resp = client.post(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
            json={"user_id": target_id, "atom_slugs": ["not_a_real_atom"]},
        )
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "user_gene.not_found"

    async def test_post_duplicate_member_409(self, client: TestClient) -> None:
        env = await _world(client)
        _token, target_id = _register(
            client, f"om-dup-{uuid.uuid4().hex[:6]}", f"dup-{uuid.uuid4().hex[:6]}@t.co"
        )
        _post_member(client, env, target_id, ["can_view_workspace"])
        resp = client.post(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
            json={"user_id": target_id, "atom_slugs": ["can_edit_workspace"]},
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "organization.member_exists"

    async def test_viewer_cannot_post(self, client: TestClient) -> None:
        env = await _world(client)
        viewer_token, viewer_id = _register(
            client, f"om-vp-{uuid.uuid4().hex[:6]}", f"vp-{uuid.uuid4().hex[:6]}@t.co"
        )
        _post_member(client, env, viewer_id, ["can_view_workspace"])
        _token, target_id = _register(
            client, f"om-vp2-{uuid.uuid4().hex[:6]}", f"vp2-{uuid.uuid4().hex[:6]}@t.co"
        )
        resp = client.post(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(viewer_token),
            json={"user_id": target_id, "atom_slugs": ["can_view_workspace"]},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

    def test_non_member_post_404(self, client: TestClient) -> None:
        _register(client, "om-np-sa", "om-np-sa@t.co")
        owner_token, _ = _register(client, "om-np-own", "om-np-own@t.co")
        org = _create_org(client, owner_token, f"np-{uuid.uuid4().hex[:6]}", "NP")
        outsider_token, _ = _register(client, "om-np-out", "om-np-out@t.co")
        _token, target_id = _register(
            client, f"om-np2-{uuid.uuid4().hex[:6]}", f"np2-{uuid.uuid4().hex[:6]}@t.co"
        )
        resp = client.post(
            f"/api/v1/organizations/{org['id']}/members",
            headers=_auth(outsider_token),
            json={"user_id": target_id, "atom_slugs": ["can_view_workspace"]},
        )
        assert resp.status_code == 404


class TestPatchMember:
    async def test_patch_replaces_gene_set_soft_deletes_old(
        self, client: TestClient, db_url: str
    ) -> None:
        env = await _world(client)
        _token, target_id = _register(
            client, f"om-pa-{uuid.uuid4().hex[:6]}", f"pa-{uuid.uuid4().hex[:6]}@t.co"
        )
        created = _post_member(
            client, env, target_id, ["can_view_workspace", "can_edit_workspace"]
        )
        contract_id = created["id"]

        resp = client.patch(
            f"/api/v1/organizations/{env['org']['id']}/members/{contract_id}",
            headers=_auth(env["owner_token"]),
            json={"atom_slugs": ["can_operate_workspace"]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert [a["slug"] for a in body["atoms"]] == ["can_operate_workspace"]
        assert body["user"]["id"] == target_id

        # Old links are soft-deleted, only the new atom stays active.
        active, gone = await _fresh_gene_rows(db_url, contract_id)
        assert [g.slug for g in active] == ["can_operate_workspace"]
        expected_old_ids = set(
            await _user_gene_ids(db_url, ["can_view_workspace", "can_edit_workspace"])
        )
        assert {g.user_gene_id for g in gone} == expected_old_ids

    async def test_patch_unknown_slug_422(self, client: TestClient) -> None:
        env = await _world(client)
        _token, target_id = _register(
            client, f"om-pb-{uuid.uuid4().hex[:6]}", f"pb-{uuid.uuid4().hex[:6]}@t.co"
        )
        created = _post_member(client, env, target_id, ["can_view_workspace"])
        resp = client.patch(
            f"/api/v1/organizations/{env['org']['id']}/members/{created['id']}",
            headers=_auth(env["owner_token"]),
            json={"atom_slugs": ["nope"]},
        )
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "user_gene.not_found"

    async def test_patch_unknown_contract_404(self, client: TestClient) -> None:
        env = await _world(client)
        resp = client.patch(
            f"/api/v1/organizations/{env['org']['id']}/members/{uuid.uuid4()}",
            headers=_auth(env["owner_token"]),
            json={"atom_slugs": ["can_view_workspace"]},
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "organization_contract.not_found"

    async def test_viewer_cannot_patch(self, client: TestClient) -> None:
        env = await _world(client)
        viewer_token, viewer_id = _register(
            client, f"om-pv-{uuid.uuid4().hex[:6]}", f"pv-{uuid.uuid4().hex[:6]}@t.co"
        )
        created = _post_member(client, env, viewer_id, ["can_view_workspace"])
        resp = client.patch(
            f"/api/v1/organizations/{env['org']['id']}/members/{created['id']}",
            headers=_auth(viewer_token),
            json={"atom_slugs": ["can_edit_workspace"]},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

    def test_non_member_patch_404(self, client: TestClient) -> None:
        _register(client, "om-pn-sa", "om-pn-sa@t.co")
        owner_token, _ = _register(client, "om-pn-own", "om-pn-own@t.co")
        org = _create_org(client, owner_token, f"pn-{uuid.uuid4().hex[:6]}", "PN")
        outsider_token, _ = _register(client, "om-pn-out", "om-pn-out@t.co")
        resp = client.patch(
            f"/api/v1/organizations/{org['id']}/members/{uuid.uuid4()}",
            headers=_auth(outsider_token),
            json={"atom_slugs": ["can_view_workspace"]},
        )
        assert resp.status_code == 404


class TestDeleteMember:
    async def test_delete_soft_deletes_contract_and_genes(
        self, client: TestClient, db_url: str
    ) -> None:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.models.organization_contract import OrganizationContract

        env = await _world(client)
        _token, target_id = _register(
            client, f"om-dl-{uuid.uuid4().hex[:6]}", f"dl-{uuid.uuid4().hex[:6]}@t.co"
        )
        created = _post_member(
            client, env, target_id, ["can_view_workspace", "can_edit_workspace"]
        )
        contract_id = created["id"]

        resp = client.delete(
            f"/api/v1/organizations/{env['org']['id']}/members/{contract_id}",
            headers=_auth(env["owner_token"]),
        )
        assert resp.status_code == 204, resp.text

        # Real deleted_at on the contract + its gene links (fresh connection).
        engine = create_async_engine(db_url)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as verify:
                row = await verify.get(OrganizationContract, contract_id)
                assert row is not None and row.deleted_at is not None
                genes = (
                    await verify.execute(
                        select(OrganizationContractGene).where(
                            OrganizationContractGene.contract_id == contract_id,
                            OrganizationContractGene.deleted_at.is_not(None),
                        )
                    )
                ).scalars().all()
                assert len(genes) == 2  # both granted atoms soft-deleted
                active = (
                    await verify.execute(
                        select(OrganizationContractGene).where(
                            OrganizationContractGene.contract_id == contract_id,
                            OrganizationContractGene.deleted_at.is_(None),
                        )
                    )
                ).scalars().all()
                assert active == []
        finally:
            await engine.dispose()

        # List no longer shows the removed member.
        resp = client.get(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1  # owner only

    async def test_delete_unknown_contract_404(self, client: TestClient) -> None:
        env = await _world(client)
        resp = client.delete(
            f"/api/v1/organizations/{env['org']['id']}/members/{uuid.uuid4()}",
            headers=_auth(env["owner_token"]),
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "organization_contract.not_found"

    async def test_viewer_cannot_delete(self, client: TestClient) -> None:
        env = await _world(client)
        viewer_token, viewer_id = _register(
            client, f"om-dv-{uuid.uuid4().hex[:6]}", f"dv-{uuid.uuid4().hex[:6]}@t.co"
        )
        created = _post_member(client, env, viewer_id, ["can_view_workspace"])
        resp = client.delete(
            f"/api/v1/organizations/{env['org']['id']}/members/{created['id']}",
            headers=_auth(viewer_token),
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"


class TestCannotLockSelf:
    """H5 防自锁 — locked: 不可剥自己最后一枚 manage_members；org 仅一人不可
    DELETE 自己的 Contract。Super-admin 绕过。"""

    async def test_patch_self_strip_400(self, client: TestClient) -> None:
        env = await _world(client)
        resp = client.get(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
        )
        own_contract_id = resp.json()["items"][0]["id"]

        patch = client.patch(
            f"/api/v1/organizations/{env['org']['id']}/members/{own_contract_id}",
            headers=_auth(env["owner_token"]),
            json={"atom_slugs": ["can_view_workspace"]},
        )
        assert patch.status_code == 400
        body = patch.json()
        assert body["error_code"] == "errors.org.cannot_lock_self"
        assert body["message_key"] == "organization.cannot_lock_self"

    async def test_delete_last_contract_400(self, client: TestClient) -> None:
        env = await _world(client)
        resp = client.get(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
        )
        assert resp.json()["total"] == 1  # org 仅一人
        own_contract_id = resp.json()["items"][0]["id"]

        deleted = client.delete(
            f"/api/v1/organizations/{env['org']['id']}/members/{own_contract_id}",
            headers=_auth(env["owner_token"]),
        )
        assert deleted.status_code == 400
        body = deleted.json()
        assert body["error_code"] == "errors.org.cannot_lock_self"
        assert body["message_key"] == "organization.cannot_lock_self"

    async def test_patch_self_keeping_manage_ok(self, client: TestClient) -> None:
        env = await _world(client)
        resp = client.get(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
        )
        own_contract_id = resp.json()["items"][0]["id"]

        patch = client.patch(
            f"/api/v1/organizations/{env['org']['id']}/members/{own_contract_id}",
            headers=_auth(env["owner_token"]),
            json={"atom_slugs": ["can_manage_org_members", "can_view_workspace"]},
        )
        assert patch.status_code == 200, patch.text
        slugs = {a["slug"] for a in patch.json()["atoms"]}
        assert "can_manage_org_members" in slugs

    async def test_delete_self_allowed_with_other_member(
        self, client: TestClient
    ) -> None:
        env = await _world(client)
        _token, other_id = _register(
            client, f"om-do-{uuid.uuid4().hex[:6]}", f"do-{uuid.uuid4().hex[:6]}@t.co"
        )
        _post_member(client, env, other_id, ["can_manage_org_members"])
        resp = client.get(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
        )
        own_contract_id = next(
            i["id"] for i in resp.json()["items"] if i["user"]["id"] == env["owner_id"]
        )

        deleted = client.delete(
            f"/api/v1/organizations/{env['org']['id']}/members/{own_contract_id}",
            headers=_auth(env["owner_token"]),
        )
        assert deleted.status_code == 204, deleted.text

    async def test_super_admin_bypasses_self_strip(self, client: TestClient) -> None:
        env = await _world(client)
        resp = client.get(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["sa_token"]),
        )
        assert resp.status_code == 200, resp.text
        own_contract_id = resp.json()["items"][0]["id"]

        patch = client.patch(
            f"/api/v1/organizations/{env['org']['id']}/members/{own_contract_id}",
            headers=_auth(env["sa_token"]),
            json={"atom_slugs": ["can_view_workspace"]},
        )
        assert patch.status_code == 200, patch.text
        assert [a["slug"] for a in patch.json()["atoms"]] == ["can_view_workspace"]

    async def test_super_admin_bypasses_last_contract_delete(
        self, client: TestClient
    ) -> None:
        env = await _world(client)
        resp = client.get(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["sa_token"]),
        )
        own_contract_id = resp.json()["items"][0]["id"]

        deleted = client.delete(
            f"/api/v1/organizations/{env['org']['id']}/members/{own_contract_id}",
            headers=_auth(env["sa_token"]),
        )
        assert deleted.status_code == 204, deleted.text

    async def test_cannot_strip_other_member_manage_atom(self, client: TestClient) -> None:
        """Stripping SOMEONE ELSE's manage atom is allowed (仅限制不可剥自己)."""
        env = await _world(client)
        _token, other_id = _register(
            client, f"om-os-{uuid.uuid4().hex[:6]}", f"os-{uuid.uuid4().hex[:6]}@t.co"
        )
        created = _post_member(client, env, other_id, ["can_manage_org_members"])

        patch = client.patch(
            f"/api/v1/organizations/{env['org']['id']}/members/{created['id']}",
            headers=_auth(env["owner_token"]),
            json={"atom_slugs": ["can_view_workspace"]},
        )
        assert patch.status_code == 200, patch.text
        assert [a["slug"] for a in patch.json()["atoms"]] == ["can_view_workspace"]


class TestCannotLockSelfV43Review:
    """v4.3 review H5+: self-DELETE (and self-PATCH) must leave the org with
    at least one contract holding can_manage_organization /
    can_manage_org_members — a zero-atom member must not be exploitable to
    permanently lock the org out of management."""

    async def test_delete_self_blocked_when_other_member_is_zero_atom(
        self, client: TestClient
    ) -> None:
        env = await _world(client)
        _token, other_id = _register(
            client, f"om-za-{uuid.uuid4().hex[:6]}", f"za-{uuid.uuid4().hex[:6]}@t.co"
        )
        _post_member(client, env, other_id, [])
        resp = client.get(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
        )
        own_contract_id = next(
            i["id"] for i in resp.json()["items"] if i["user"]["id"] == env["owner_id"]
        )

        deleted = client.delete(
            f"/api/v1/organizations/{env['org']['id']}/members/{own_contract_id}",
            headers=_auth(env["owner_token"]),
        )
        assert deleted.status_code == 400
        assert deleted.json()["error_code"] == "errors.org.cannot_lock_self"

    async def test_delete_self_blocked_when_other_member_viewer_only(
        self, client: TestClient
    ) -> None:
        env = await _world(client)
        _token, other_id = _register(
            client, f"om-vo-{uuid.uuid4().hex[:6]}", f"vo-{uuid.uuid4().hex[:6]}@t.co"
        )
        _post_member(client, env, other_id, ["can_view_workspace"])
        resp = client.get(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
        )
        own_contract_id = next(
            i["id"] for i in resp.json()["items"] if i["user"]["id"] == env["owner_id"]
        )

        deleted = client.delete(
            f"/api/v1/organizations/{env['org']['id']}/members/{own_contract_id}",
            headers=_auth(env["owner_token"]),
        )
        assert deleted.status_code == 400
        assert deleted.json()["error_code"] == "errors.org.cannot_lock_self"

    async def test_delete_self_allowed_when_other_holds_manage_organization(
        self, client: TestClient
    ) -> None:
        env = await _world(client)
        _token, other_id = _register(
            client, f"om-mo-{uuid.uuid4().hex[:6]}", f"mo-{uuid.uuid4().hex[:6]}@t.co"
        )
        _post_member(client, env, other_id, ["can_manage_organization"])
        resp = client.get(
            f"/api/v1/organizations/{env['org']['id']}/members",
            headers=_auth(env["owner_token"]),
        )
        own_contract_id = next(
            i["id"] for i in resp.json()["items"] if i["user"]["id"] == env["owner_id"]
        )

        deleted = client.delete(
            f"/api/v1/organizations/{env['org']['id']}/members/{own_contract_id}",
            headers=_auth(env["owner_token"]),
        )
        assert deleted.status_code == 204, deleted.text


class TestConcurrentMemberAddRace:
    """v4.3 review: a lost-update duplicate add (partial unique index firing
    between the pre-check and the insert) must map to 409, not a 500."""

    @pytest.mark.asyncio
    async def test_integrity_error_maps_to_409(
        self, client: TestClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from sqlalchemy.exc import IntegrityError

        from app.api.v1 import organizations as org_api
        from app.core.errors import ConflictError
        from app.schemas.auth import CurrentUser
        from app.schemas.organization import OrganizationMemberCreate

        _register(client, "om-race-sa", "om-race-sa@t.co")
        owner_token, owner_id = _register(
            client, f"om-race-own-{uuid.uuid4().hex[:6]}", "race-own@t.co"
        )
        org = _create_org(client, owner_token, f"race-{uuid.uuid4().hex[:6]}", "Race")
        _target_token, target_id = _register(
            client, f"om-race-tgt-{uuid.uuid4().hex[:6]}", "race-tgt@t.co"
        )

        async def racy_ensure(db, *, organization_id, user_id, source_pack=None):
            raise IntegrityError(
                "INSERT",
                {},
                Exception(
                    "duplicate key value violates unique constraint "
                    "uq_organization_contracts_org_user"
                ),
            )

        monkeypatch.setattr(org_api, "ensure_org_contract", racy_ensure)

        cu = CurrentUser(user_id=owner_id, is_super_admin=False, token="t")
        with pytest.raises(ConflictError) as exc_info:
            await org_api.create_org_member(
                org["id"],
                OrganizationMemberCreate(
                    user_id=target_id, atom_slugs=["can_view_workspace"]
                ),
                db=session,
                current_user=cu,
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.error_code == "organization.member_exists"

        # rollback was called — no orphan contract row remains.
        from app.models.organization_contract import OrganizationContract

        rows = (
            await session.execute(
                select(OrganizationContract).where(
                    OrganizationContract.organization_id == org["id"],
                    OrganizationContract.user_id == target_id,
                )
            )
        ).scalars().all()
        assert rows == []


async def _user_gene_ids(db_url: str, slugs: list[str]) -> list[str]:
    """Resolve UserGene ids for slugs through a fresh connection."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as s:
            rows = (
                await s.execute(
                    select(UserGene).where(
                        UserGene.slug.in_(slugs), UserGene.deleted_at.is_(None)
                    )
                )
            ).scalars().all()
            return [g.id for g in rows]
    finally:
        await engine.dispose()
