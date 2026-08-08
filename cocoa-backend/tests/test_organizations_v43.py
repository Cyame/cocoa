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

    def test_zero_atom_contract_org_not_listed(self, client: TestClient) -> None:
        """Design §3.6: 0 active atom genes = 无权访问 — OrgPicker excludes it.

        A zero-atom contract must not surface the org; granting any atom
        makes it visible again.
        """
        _register(client, "list-za-sa", "list-za-sa@test.com")
        owner_token, _ = _register(client, "list-za-own", "list-za-own@test.com")
        org = _create_org(
            client, owner_token, f"list-za-{uuid.uuid4().hex[:6]}", "Org ZA"
        )
        zero_token, zero_id = _register(client, "list-za-z", "list-za-z@test.com")

        resp = client.post(
            f"/api/v1/organizations/{org['id']}/members",
            headers=_auth(owner_token),
            json={"user_id": zero_id, "atom_slugs": []},
        )
        assert resp.status_code == 201, resp.text
        contract_id = resp.json()["id"]

        resp = client.get("/api/v1/organizations", headers=_auth(zero_token))
        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert resp.json()["total"] == 0

        # Granting an atom flips the contract back to valid.
        patched = client.patch(
            f"/api/v1/organizations/{org['id']}/members/{contract_id}",
            headers=_auth(owner_token),
            json={"atom_slugs": ["can_view_workspace"]},
        )
        assert patched.status_code == 200, patched.text
        resp = client.get("/api/v1/organizations", headers=_auth(zero_token))
        assert resp.status_code == 200
        assert [i["id"] for i in resp.json()["items"]] == [org["id"]]


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

    def test_zero_atom_contract_holder_gets_404(self, client: TestClient) -> None:
        """Design §3.6: zero-atom contract = no access (404, no existence leak)."""
        _register(client, "get-za-sa", "get-za-sa@test.com")
        owner_token, _ = _register(client, "get-za-own", "get-za-own@test.com")
        org = _create_org(
            client, owner_token, f"get-za-{uuid.uuid4().hex[:6]}", "Org"
        )
        zero_token, zero_id = _register(client, "get-za-z", "get-za-z@test.com")
        resp = client.post(
            f"/api/v1/organizations/{org['id']}/members",
            headers=_auth(owner_token),
            json={"user_id": zero_id, "atom_slugs": []},
        )
        assert resp.status_code == 201, resp.text

        resp = client.get(
            f"/api/v1/organizations/{org['id']}", headers=_auth(zero_token)
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "organization.not_found"


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
        memberships + entities + instances + knowledge rows, and filters
        exclude them."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.models.entity import Entity
        from app.models.instance import Instance
        from app.models.knowledge import KnowledgeDimension, KnowledgeEntry
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
        entity = Entity(namespace_id=ns.id, name="E One", slug="e-1")
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
        dim = KnowledgeDimension(
            organization_id=org["id"],
            scope="org",
            slug=f"dim-{uuid.uuid4().hex[:6]}",
            name="Org Dimension",
        )
        session.add(dim)
        await session.flush()
        entry = KnowledgeEntry(
            organization_id=org["id"],
            scope="org",
            key=f"key-{uuid.uuid4().hex[:6]}",
            title="Org Entry",
            body="body",
            dimension_id=dim.id,
        )
        session.add(entry)
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

                dim_row = await verify.get(KnowledgeDimension, dim.id)
                assert dim_row is not None and dim_row.deleted_at is not None
                entry_row = await verify.get(KnowledgeEntry, entry.id)
                assert entry_row is not None and entry_row.deleted_at is not None

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
    async def test_header_org_zero_atom_contract_forbidden(
        self, session: AsyncSession, create_org_bundle
    ) -> None:
        """Design §3.6: a zero-atom contract is not org access — 403.

        (v4.3 review: this pins the new behavior; a zero-atom contract was
        previously treated as a valid membership.)
        """
        from app.api.deps import get_current_org
        from app.core.errors import ForbiddenError
        from app.models.organization import Organization

        user_id = await self._make_user(session)
        member_org = Organization(slug=f"cd-za-{uuid.uuid4().hex[:6]}", name="Zero Atom Org")
        session.add(member_org)
        await session.flush()
        await create_org_bundle(user_id, atoms=(), organization=member_org)
        await session.commit()

        cu = CurrentUser(user_id=user_id, is_super_admin=False, token="t")
        with pytest.raises(ForbiddenError):
            await get_current_org(session, cu, member_org.id)

    @pytest.mark.asyncio
    async def test_header_org_resolves(self, session: AsyncSession, create_org_bundle) -> None:
        """X-Organization-Id resolves when the contract holds >= 1 atom."""
        from app.api.deps import get_current_org
        from app.core.errors import ForbiddenError, NotFoundError
        from app.models.organization import Organization

        user_id = await self._make_user(session)
        member_org = Organization(slug=f"cd-m-{uuid.uuid4().hex[:6]}", name="Member Org")
        session.add(member_org)
        await session.flush()
        await create_org_bundle(
            user_id, atoms=("can_view_workspace",), organization=member_org
        )
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


class TestOrgScopedProviders:
    """v4.3 review: providers are org-scoped — a non-default org configures
    its own LLM providers under /organizations/{id}/providers; the /default/*
    routes stay as super-admin-gated aliases."""

    def _provider_payload(self, slug: str) -> dict:
        return {
            "origin": "custom",
            "name": f"Gateway {slug}",
            "slug": slug,
            "request_format": "completion",
            "base_url": "https://llm.example.com/v1",
            "api_key_ref": f"{slug.upper()}_KEY",
            "default_model": "gpt-4o-mini",
        }

    def test_crud_round_trip_on_non_default_org(self, client: TestClient) -> None:
        _register(client, "osp-sa", "osp-sa@t.co")
        owner_token, _ = _register(client, "osp-own", "osp-own@t.co")
        org = _create_org(client, owner_token, f"osp-{uuid.uuid4().hex[:6]}", "Scoped")

        created = client.post(
            f"/api/v1/organizations/{org['id']}/providers",
            headers=_auth(owner_token),
            json=self._provider_payload("scoped-gw"),
        )
        assert created.status_code == 201, created.text
        pid = created.json()["id"]
        assert created.json()["organization_id"] == org["id"]

        listed = client.get(
            f"/api/v1/organizations/{org['id']}/providers",
            headers=_auth(owner_token),
        )
        assert listed.status_code == 200
        assert [p["id"] for p in listed.json()] == [pid]

        got = client.get(
            f"/api/v1/organizations/{org['id']}/providers/{pid}",
            headers=_auth(owner_token),
        )
        assert got.status_code == 200
        assert got.json()["slug"] == "scoped-gw"

        patched = client.patch(
            f"/api/v1/organizations/{org['id']}/providers/{pid}",
            headers=_auth(owner_token),
            json={"enabled": False},
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["enabled"] is False

        deleted = client.delete(
            f"/api/v1/organizations/{org['id']}/providers/{pid}",
            headers=_auth(owner_token),
        )
        assert deleted.status_code == 204
        gone = client.get(
            f"/api/v1/organizations/{org['id']}/providers/{pid}",
            headers=_auth(owner_token),
        )
        assert gone.status_code == 404

    def test_providers_isolated_between_orgs(self, client: TestClient) -> None:
        _register(client, "osp-iso-sa", "osp-iso-sa@t.co")
        owner_token, _ = _register(client, "osp-iso-own", "osp-iso-own@t.co")
        org_a = _create_org(client, owner_token, f"ospa-{uuid.uuid4().hex[:6]}", "A")
        org_b = _create_org(client, owner_token, f"ospb-{uuid.uuid4().hex[:6]}", "B")

        created = client.post(
            f"/api/v1/organizations/{org_a['id']}/providers",
            headers=_auth(owner_token),
            json=self._provider_payload("iso-gw"),
        )
        assert created.status_code == 201, created.text

        listed_b = client.get(
            f"/api/v1/organizations/{org_b['id']}/providers",
            headers=_auth(owner_token),
        )
        assert listed_b.status_code == 200
        assert listed_b.json() == []

    def test_system_hub_and_cerebellum_defaults_org_scoped(
        self, client: TestClient
    ) -> None:
        _register(client, "osp-hub-sa", "osp-hub-sa@t.co")
        owner_token, _ = _register(client, "osp-hub-own", "osp-hub-own@t.co")
        org = _create_org(client, owner_token, f"osph-{uuid.uuid4().hex[:6]}", "Hub")

        created = client.post(
            f"/api/v1/organizations/{org['id']}/providers",
            headers=_auth(owner_token),
            json=self._provider_payload("hub-gw"),
        )
        assert created.status_code == 201, created.text
        pid = created.json()["id"]

        hub = client.post(
            f"/api/v1/organizations/{org['id']}/providers/{pid}/set-default",
            headers=_auth(owner_token),
            json={"target": "system_hub", "model": "gpt-4o"},
        )
        assert hub.status_code == 200, hub.text
        assert hub.json()["provider_id"] == pid

        got_hub = client.get(
            f"/api/v1/organizations/{org['id']}/system-hub",
            headers=_auth(owner_token),
        )
        assert got_hub.status_code == 200
        assert got_hub.json()["configured"] is True
        assert got_hub.json()["provider_id"] == pid

        cer = client.post(
            f"/api/v1/organizations/{org['id']}/providers/{pid}/set-default",
            headers=_auth(owner_token),
            json={"target": "cerebellum", "model": "deepseek-r1"},
        )
        assert cer.status_code == 200, cer.text
        got_cer = client.get(
            f"/api/v1/organizations/{org['id']}/cerebellum-defaults",
            headers=_auth(owner_token),
        )
        assert got_cer.json()["provider_id"] == pid
        assert got_cer.json()["model"] == "deepseek-r1"

        other = _create_org(
            client, owner_token, f"osph2-{uuid.uuid4().hex[:6]}", "H2"
        )
        other_hub = client.get(
            f"/api/v1/organizations/{other['id']}/system-hub",
            headers=_auth(owner_token),
        )
        assert other_hub.json()["configured"] is False

    def test_preview_models_org_scoped(self, client: TestClient) -> None:
        from unittest.mock import AsyncMock, patch

        _register(client, "osp-pv-sa", "osp-pv-sa@t.co")
        owner_token, _ = _register(client, "osp-pv-own", "osp-pv-own@t.co")
        org = _create_org(client, owner_token, f"ospv-{uuid.uuid4().hex[:6]}", "PV")

        with patch(
            "app.api.v1.organizations.fetch_models_from_endpoint",
            new=AsyncMock(
                return_value=([{"id": "m1", "name": "M1", "provider": "p"}], None)
            ),
        ):
            resp = client.post(
                f"/api/v1/organizations/{org['id']}/providers/preview-models",
                headers=_auth(owner_token),
                json={
                    "api_key_ref": "K",
                    "base_url": "https://llm.example.com/v1",
                    "request_format": "completion",
                },
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"][0]["id"] == "m1"

    def test_write_requires_can_manage_organization(self, client: TestClient) -> None:
        _register(client, "osp-pm-sa", "osp-pm-sa@t.co")
        owner_token, _ = _register(client, "osp-pm-own", "osp-pm-own@t.co")
        org = _create_org(client, owner_token, f"ospp-{uuid.uuid4().hex[:6]}", "PM")
        viewer_token, viewer_id = _register(client, "osp-pm-vw", "osp-pm-vw@t.co")

        added = client.post(
            f"/api/v1/organizations/{org['id']}/members",
            headers=_auth(owner_token),
            json={"user_id": viewer_id, "atom_slugs": ["can_view_workspace"]},
        )
        assert added.status_code == 201, added.text

        resp = client.post(
            f"/api/v1/organizations/{org['id']}/providers",
            headers=_auth(viewer_token),
            json=self._provider_payload("viewer-gw"),
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

        listed = client.get(
            f"/api/v1/organizations/{org['id']}/providers",
            headers=_auth(viewer_token),
        )
        assert listed.status_code == 200

    def test_non_member_gets_404(self, client: TestClient) -> None:
        _register(client, "osp-nm-sa", "osp-nm-sa@t.co")
        owner_token, _ = _register(client, "osp-nm-own", "osp-nm-own@t.co")
        org = _create_org(client, owner_token, f"ospn-{uuid.uuid4().hex[:6]}", "NM")
        outsider_token, _ = _register(client, "osp-nm-out", "osp-nm-out@t.co")

        resp = client.get(
            f"/api/v1/organizations/{org['id']}/providers",
            headers=_auth(outsider_token),
        )
        assert resp.status_code == 404

    def test_default_alias_still_works(self, client: TestClient) -> None:
        """/default/* provider routes keep working: reads for any logged-in
        user, writes super-admin only."""
        _register(client, "osp-df-sa", "osp-df-sa@t.co")
        owner_token, _ = _register(client, "osp-df-own", "osp-df-own@t.co")

        listed = client.get(
            "/api/v1/organizations/default/providers", headers=_auth(owner_token)
        )
        assert listed.status_code == 200

        resp = client.post(
            "/api/v1/organizations/default/providers",
            headers=_auth(owner_token),
            json=self._provider_payload("df-gw"),
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "auth.super_admin_required"
