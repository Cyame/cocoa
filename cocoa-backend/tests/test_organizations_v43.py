"""v4-3 backend lane: CurrentOrg dependency + org-by-id CRUD + proxy fields.

Covers:
- CurrentOrg dependency: header validation, 404/400 semantics.
- GET /organizations: only orgs with valid OrganizationContracts.
- GET /organizations/{id}: 404 for non-member (no existence leak).
- PATCH /organizations/{id}: requires can_manage_organization (403).
- DELETE /organizations/{id}: cascade soft-delete (deleted_at set on org +
  namespaces + workspaces + org contracts + memberships + entities +
  instances; query filters exclude them).
- Proxy fields round-trip on create / patch / read.
- Super-admin bypass on by-id CRUD.
- POST /organizations still returns id (B3 regression).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.schemas.auth import CurrentUser


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, username: str, email: str) -> tuple[str, str]:
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


def _create_org(client: TestClient, token: str, slug: str, name: str, **extra) -> dict:
    resp = client.post(
        "/api/v1/organizations",
        headers=_auth(token),
        json={"slug": slug, "name": name, **extra},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


class TestListOrganizations:
    def test_only_orgs_with_valid_contracts(self, client: TestClient) -> None:
        """GET /organizations returns only orgs the caller has a contract in."""
        _register(client, "list-admin", "list-admin@test.com")
        member_token, member_id = _register(client, "list-mem", "list-mem@test.com")

        org_a = _create_org(
            client, member_token, f"list-a-{uuid.uuid4().hex[:6]}", "Org A"
        )
        org_b = _create_org(
            client, member_token, f"list-b-{uuid.uuid4().hex[:6]}", "Org B"
        )

        resp = client.get("/api/v1/organizations", headers=_auth(member_token))
        assert resp.status_code == 200
        body = resp.json()
        ids = {item["id"] for item in body["items"]}
        assert org_a["id"] in ids
        assert org_b["id"] in ids
        assert body["total"] == 2

    def test_empty_for_user_without_contracts(self, client: TestClient) -> None:
        _register(client, "list-admin2", "list-admin2@test.com")
        other_token, _ = _register(client, "list-other", "list-other@test.com")
        _create_org(
            client, other_token, f"list-x-{uuid.uuid4().hex[:6]}", "Org X"
        )

        no_contract_token, _ = _register(
            client, "list-nc", "list-nc@test.com"
        )
        resp = client.get("/api/v1/organizations", headers=_auth(no_contract_token))
        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert resp.json()["total"] == 0


class TestGetOrganization:
    def test_member_can_get(self, client: TestClient) -> None:
        _register(client, "get-admin", "get-admin@test.com")
        member_token, _ = _register(client, "get-mem", "get-mem@test.com")
        org = _create_org(client, member_token, f"get-a-{uuid.uuid4().hex[:6]}", "Org")
        resp = client.get(f"/api/v1/organizations/{org['id']}", headers=_auth(member_token))
        assert resp.status_code == 200
        assert resp.json()["id"] == org["id"]

    def test_non_member_gets_404_not_403(self, client: TestClient) -> None:
        """Non-members must not learn the org exists (404, not 403)."""
        _register(client, "get-admin2", "get-admin2@test.com")
        owner_token, _ = _register(client, "get-owner", "get-owner@test.com")
        org = _create_org(client, owner_token, f"get-b-{uuid.uuid4().hex[:6]}", "Org")
        outsider_token, _ = _register(client, "get-out", "get-out@test.com")

        resp = client.get(f"/api/v1/organizations/{org['id']}", headers=_auth(outsider_token))
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "organization.not_found"

    def test_missing_org_404(self, client: TestClient) -> None:
        _register(client, "get-admin3", "get-admin3@test.com")
        member_token, _ = _register(client, "get-mem3", "get-mem3@test.com")
        resp = client.get(
            f"/api/v1/organizations/{uuid.uuid4()}",
            headers=_auth(member_token),
        )
        assert resp.status_code == 404


class TestPatchOrganization:
    @pytest.mark.asyncio
    async def test_requires_can_manage_organization(self, client: TestClient, session: AsyncSession) -> None:
        """A member without can_manage_organization gets 403 on PATCH."""
        from app.core.gene_atoms import ensure_atom_genes
        from app.core.org_contract import ensure_org_contract, grant_atoms

        _register(client, "patch-admin", "patch-admin@test.com")
        owner_token, _ = _register(client, "patch-owner", "patch-owner@test.com")
        org = _create_org(client, owner_token, f"patch-a-{uuid.uuid4().hex[:6]}", "Org")
        viewer_token, viewer_id = _register(client, "patch-viewer", "patch-viewer@test.com")

        await ensure_atom_genes(session)
        contract = await ensure_org_contract(
            session, organization_id=org["id"], user_id=viewer_id
        )
        await grant_atoms(session, contract.id, ("can_view_workspace",))
        await session.commit()

        resp = client.patch(
            f"/api/v1/organizations/{org['id']}",
            headers=_auth(viewer_token),
            json={"name": "Hacked"},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

    def test_member_with_atom_can_update(self, client: TestClient) -> None:
        _register(client, "patch-admin2", "patch-admin2@test.com")
        owner_token, _ = _register(client, "patch-owner2", "patch-owner2@test.com")
        org = _create_org(client, owner_token, f"patch-b-{uuid.uuid4().hex[:6]}", "Org")

        resp = client.patch(
            f"/api/v1/organizations/{org['id']}",
            headers=_auth(owner_token),
            json={
                "name": "Renamed",
                "description": "hello",
                "system_hub_model": "gpt-4o",
                "cerebellum_default_model": "deepseek-r1",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "Renamed"
        assert body["description"] == "hello"
        assert body["system_hub_model"] == "gpt-4o"
        assert body["cerebellum_default_model"] == "deepseek-r1"

    def test_non_member_patch_404(self, client: TestClient) -> None:
        _register(client, "patch-admin3", "patch-admin3@test.com")
        owner_token, _ = _register(client, "patch-owner3", "patch-owner3@test.com")
        org = _create_org(client, owner_token, f"patch-c-{uuid.uuid4().hex[:6]}", "Org")
        outsider_token, _ = _register(client, "patch-out3", "patch-out3@test.com")

        resp = client.patch(
            f"/api/v1/organizations/{org['id']}",
            headers=_auth(outsider_token),
            json={"name": "Nope"},
        )
        assert resp.status_code == 404


class TestDeleteOrganization:
    @pytest.mark.asyncio
    async def test_cascade_soft_delete(
        self, client: TestClient, session: AsyncSession, db_url: str
    ) -> None:
        """DELETE soft-deletes org + namespaces + workspaces + contracts +
        memberships + entities + instances, and filters exclude them."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.models.entity import Entity
        from app.models.instance import Instance
        from app.models.organization import Namespace, Organization
        from app.models.organization_contract import OrganizationContract
        from app.models.workspace import Membership, Workspace

        _register(client, "del-admin", "del-admin@test.com")
        owner_token, owner_id = _register(client, "del-owner", "del-owner@test.com")
        org = _create_org(client, owner_token, f"del-a-{uuid.uuid4().hex[:6]}", "Org")

        ns = Namespace(org_id=org["id"], slug="ns-1", name="NS One")
        session.add(ns)
        await session.flush()
        ws = Workspace(namespace_id=ns.id, name="WS One", slug="ws-1")
        session.add(ws)
        await session.flush()
        entity = Entity(namespace_id=ns.id, name="E One", slug="e-1", rank="intern")
        session.add(entity)
        await session.flush()
        inst = Instance(
            entity_id=entity.id,
            workspace_id=ws.id,
            status="creating",
            proxy_token=str(uuid.uuid4()),
        )
        session.add(inst)
        await session.flush()
        membership = Membership(workspace_id=ws.id, user_id=owner_id, posx=0, posy=0)
        session.add(membership)
        await session.commit()

        resp = client.delete(
            f"/api/v1/organizations/{org['id']}",
            headers=_auth(owner_token),
        )
        assert resp.status_code == 204

        # Read back through a fresh connection so the assertions see the real
        # DB state (the fixture session identity-map caches pre-delete rows).
        engine = create_async_engine(db_url)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as verify:
                db_org = await verify.get(Organization, org["id"])
                assert db_org is not None and db_org.deleted_at is not None

                ns_row = await verify.get(Namespace, ns.id)
                assert ns_row is not None and ns_row.deleted_at is not None
                ws_row = await verify.get(Workspace, ws.id)
                assert ws_row is not None and ws_row.deleted_at is not None
                entity_row = await verify.get(Entity, entity.id)
                assert entity_row is not None and entity_row.deleted_at is not None
                inst_row = await verify.get(Instance, inst.id)
                assert inst_row is not None and inst_row.deleted_at is not None
                mem_row = await verify.get(Membership, membership.id)
                assert mem_row is not None and mem_row.deleted_at is not None

                contracts = (
                    await verify.execute(
                        select(OrganizationContract).where(
                            OrganizationContract.organization_id == org["id"],
                            OrganizationContract.deleted_at.is_(None),
                        )
                    )
                ).scalars().all()
                assert contracts == []
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_requires_can_manage_organization(self, client: TestClient, session: AsyncSession) -> None:
        from app.core.gene_atoms import ensure_atom_genes
        from app.core.org_contract import ensure_org_contract, grant_atoms

        _register(client, "del-admin2", "del-admin2@test.com")
        owner_token, _ = _register(client, "del-owner2", "del-owner2@test.com")
        org = _create_org(client, owner_token, f"del-b-{uuid.uuid4().hex[:6]}", "Org")
        viewer_token, viewer_id = _register(client, "del-viewer2", "del-viewer2@test.com")

        await ensure_atom_genes(session)
        contract = await ensure_org_contract(
            session, organization_id=org["id"], user_id=viewer_id
        )
        await grant_atoms(session, contract.id, ("can_view_workspace",))
        await session.commit()

        resp = client.delete(
            f"/api/v1/organizations/{org['id']}",
            headers=_auth(viewer_token),
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

    def test_non_member_delete_404(self, client: TestClient) -> None:
        _register(client, "del-admin3", "del-admin3@test.com")
        owner_token, _ = _register(client, "del-owner3", "del-owner3@test.com")
        org = _create_org(client, owner_token, f"del-c-{uuid.uuid4().hex[:6]}", "Org")
        outsider_token, _ = _register(client, "del-out3", "del-out3@test.com")

        resp = client.delete(
            f"/api/v1/organizations/{org['id']}",
            headers=_auth(outsider_token),
        )
        assert resp.status_code == 404


class TestProxyFields:
    def test_round_trip_create_patch_get(self, client: TestClient) -> None:
        _register(client, "px-admin", "px-admin@test.com")
        owner_token, _ = _register(client, "px-owner", "px-owner@test.com")

        org = _create_org(
            client,
            owner_token,
            f"px-a-{uuid.uuid4().hex[:6]}",
            "Org",
            use_proxy=True,
            proxy_host="proxy.corp.local",
            proxy_port=8080,
            proxy_username="alice",
            proxy_password="s3cret",
        )
        assert org["use_proxy"] is True
        assert org["proxy_host"] == "proxy.corp.local"
        assert org["proxy_port"] == 8080
        assert org["proxy_username"] == "alice"
        assert org["proxy_password"] == "s3cret"

        patched = client.patch(
            f"/api/v1/organizations/{org['id']}",
            headers=_auth(owner_token),
            json={"proxy_host": "proxy2.corp.local", "use_proxy": False},
        )
        assert patched.status_code == 200, patched.text
        body = patched.json()
        assert body["proxy_host"] == "proxy2.corp.local"
        assert body["use_proxy"] is False
        assert body["proxy_port"] == 8080

        got = client.get(
            f"/api/v1/organizations/{org['id']}",
            headers=_auth(owner_token),
        )
        assert got.status_code == 200
        assert got.json()["proxy_username"] == "alice"
        assert got.json()["proxy_password"] == "s3cret"

    def test_defaults_false_and_null(self, client: TestClient) -> None:
        _register(client, "px-admin2", "px-admin2@test.com")
        owner_token, _ = _register(client, "px-owner2", "px-owner2@test.com")
        org = _create_org(client, owner_token, f"px-b-{uuid.uuid4().hex[:6]}", "Org")
        assert org["use_proxy"] is False
        assert org["proxy_host"] is None
        assert org["proxy_port"] is None


class TestSuperAdminBypass:
    def test_super_admin_can_get_patch_delete_any_org(self, client: TestClient) -> None:
        admin_token, _ = _register(client, "sa-admin", "sa-admin@test.com")
        owner_token, _ = _register(client, "sa-owner", "sa-owner@test.com")
        org = _create_org(client, owner_token, f"sa-a-{uuid.uuid4().hex[:6]}", "Org")

        got = client.get(f"/api/v1/organizations/{org['id']}", headers=_auth(admin_token))
        assert got.status_code == 200

        patched = client.patch(
            f"/api/v1/organizations/{org['id']}",
            headers=_auth(admin_token),
            json={"name": "Admin Rename"},
        )
        assert patched.status_code == 200, patched.text

        deleted = client.delete(
            f"/api/v1/organizations/{org['id']}",
            headers=_auth(admin_token),
        )
        assert deleted.status_code == 204


class TestCreateRegression:
    def test_post_returns_id(self, client: TestClient) -> None:
        """B3 regression: POST /organizations body must include id."""
        _register(client, "post-admin", "post-admin@test.com")
        member_token, _ = _register(client, "post-mem", "post-mem@test.com")
        org = _create_org(client, member_token, f"post-a-{uuid.uuid4().hex[:6]}", "Org")
        assert org["id"]
        assert org["slug"]

    def test_zero_contract_user_can_create(self, client: TestClient) -> None:
        """B3 bypass: logged-in user with 0 contracts may create an org."""
        _register(client, "post-admin2", "post-admin2@test.com")
        fresh_token, _ = _register(client, "post-fresh", "post-fresh@test.com")
        org = _create_org(client, fresh_token, f"post-b-{uuid.uuid4().hex[:6]}", "Org")
        assert org["id"]


class TestCurrentOrgDependency:
    async def _make_user(self, session: AsyncSession, *, is_super_admin: bool = False) -> str:
        from app.core.security import hash_password
        from app.models.user import User

        user = User(
            username=f"cd-{uuid.uuid4().hex[:8]}",
            email=f"cd-{uuid.uuid4().hex[:8]}@test.com",
            password_hash=hash_password("password123"),
            is_super_admin=is_super_admin,
        )
        session.add(user)
        await session.flush()
        return user.id

    @pytest.mark.asyncio
    async def test_header_org_resolves(self, session: AsyncSession, create_org_bundle) -> None:
        from app.api.deps import get_current_org
        from app.core.errors import ForbiddenError, NotFoundError
        from app.models.organization import Organization

        user_id = await self._make_user(session)
        member_org = Organization(slug=f"cd-m-{uuid.uuid4().hex[:6]}", name="Member Org")
        session.add(member_org)
        await session.flush()
        await create_org_bundle(user_id, atoms=(), organization=member_org)
        await session.commit()

        cu = CurrentUser(user_id=user_id, is_super_admin=False, token="t")
        org_id = await get_current_org(session, cu, member_org.id)
        assert org_id == member_org.id

        # Unknown org id in header → 404 (NotFoundError).
        with pytest.raises(NotFoundError):
            await get_current_org(session, cu, str(uuid.uuid4()))

        # Non-member on a different org → 403 (ForbiddenError).
        other_org = Organization(slug=f"cd-o-{uuid.uuid4().hex[:6]}", name="Other Org")
        session.add(other_org)
        await session.commit()
        with pytest.raises(ForbiddenError):
            await get_current_org(session, cu, other_org.id)

    @pytest.mark.asyncio
    async def test_super_admin_bypasses_membership(self, session: AsyncSession) -> None:
        from app.api.deps import get_current_org
        from app.models.organization import Organization

        admin_id = await self._make_user(session, is_super_admin=True)
        org = Organization(slug=f"cd-sa-{uuid.uuid4().hex[:6]}", name="SA Org")
        session.add(org)
        await session.commit()

        cu = CurrentUser(user_id=admin_id, is_super_admin=True, token="t")
        org_id = await get_current_org(session, cu, org.id)
        assert org_id == org.id

    @pytest.mark.asyncio
    async def test_no_header_single_contract_resolves(self, session: AsyncSession) -> None:
        from app.api.deps import get_current_org
        from app.core.gene_atoms import ensure_atom_genes
        from app.core.org_contract import ensure_org_contract
        from app.models.organization import Organization

        user_id = await self._make_user(session)
        org = Organization(slug=f"cd-{uuid.uuid4().hex[:6]}", name="CD Org")
        session.add(org)
        await session.flush()
        await ensure_atom_genes(session)
        await ensure_org_contract(session, organization_id=org.id, user_id=user_id)
        await session.commit()

        cu = CurrentUser(user_id=user_id, is_super_admin=False, token="t")
        org_id = await get_current_org(session, cu, None)
        assert org_id == org.id

    @pytest.mark.asyncio
    async def test_ambiguous_context_raises_400(self, session: AsyncSession) -> None:
        from app.api.deps import get_current_org
        from app.core.errors import CocoaError
        from app.core.gene_atoms import ensure_atom_genes
        from app.core.org_contract import ensure_org_contract
        from app.models.organization import Organization

        user_id = await self._make_user(session)
        await ensure_atom_genes(session)
        for i in range(2):
            org = Organization(slug=f"cd-{i}-{uuid.uuid4().hex[:6]}", name=f"CD {i}")
            session.add(org)
            await session.flush()
            await ensure_org_contract(
                session, organization_id=org.id, user_id=user_id
            )
        await session.commit()

        cu = CurrentUser(user_id=user_id, is_super_admin=False, token="t")
        with pytest.raises(CocoaError) as exc_info:
            await get_current_org(session, cu, None)
        assert exc_info.value.status_code == 400
        assert exc_info.value.error_code == "organization.context_required"
