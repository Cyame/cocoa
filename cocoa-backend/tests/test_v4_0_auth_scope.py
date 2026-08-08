"""v4.0 acceptance tests — schema / scope / gene-only auth.

Covers the slice's acceptance list (`.omo/plans/v4-0-schema-auth-scope.md`):
- require_permission layering (org contract, namespace union, super-admin)
- operate-vs-edit atom distinction
- POST /organizations B3 bypass + creator atom seed
- system-scope write guard (4xx)
- overlay reading the entity_capabilities junction
- X-Organization-Id mismatch rejection
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.core.errors import ForbiddenError
from app.core.permissions import (
    require_workspace_permission,
)
from app.models.user import User


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_user(session: AsyncSession, *, super_admin: bool = False) -> User:
    user = User(
        username=f"v40-{uuid.uuid4().hex[:8]}",
        email=f"v40-{uuid.uuid4().hex[:8]}@test.com",
        password_hash="x",
        is_super_admin=super_admin,
    )
    session.add(user)
    await session.flush()
    return user


class TestRequirePermission:
    @pytest.mark.asyncio
    async def test_org_grant_allows(
        self, session: AsyncSession, workspace_factory, create_org_bundle
    ) -> None:
        user = await _make_user(session)
        workspace = await workspace_factory()
        await create_org_bundle(user.id, atoms=("can_view_workspace",), workspace=workspace)

        await require_workspace_permission(
            session, user.id, workspace.id, "can_view_workspace"
        )

    @pytest.mark.asyncio
    async def test_denied_without_grant(
        self, session: AsyncSession, workspace_factory
    ) -> None:
        user = await _make_user(session)
        workspace = await workspace_factory()

        with pytest.raises(ForbiddenError) as exc:
            await require_workspace_permission(
                session, user.id, workspace.id, "can_view_workspace"
            )
        assert exc.value.error_code == "permission.denied"

    @pytest.mark.asyncio
    async def test_namespace_union_adds_atoms(
        self, session: AsyncSession, workspace_factory, create_org_bundle
    ) -> None:
        """NamespaceContract genes union on top of the OrgContract grant."""
        from app.core.namespace_contract import ensure_namespace_contract
        from app.models.namespace_contract import NamespaceContractGene
        from app.models.user_gene import UserGene

        user = await _make_user(session)
        workspace = await workspace_factory()
        # Org grant: view only.
        bundle = await create_org_bundle(
            user.id, atoms=("can_view_workspace",), workspace=workspace
        )

        # Edit denied at this point.
        with pytest.raises(ForbiddenError):
            await require_workspace_permission(
                session, user.id, workspace.id, "can_edit_workspace"
            )

        # NS grant adds edit.
        ns_contract = await ensure_namespace_contract(
            session, namespace_id=bundle.namespace.id, user_id=user.id
        )
        edit_gene = (
            await session.execute(
                select(UserGene).where(
                    UserGene.slug == "can_edit_workspace",
                    UserGene.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        session.add(
            NamespaceContractGene(
                contract_id=ns_contract.id, user_gene_id=edit_gene.id
            )
        )
        await session.flush()

        await require_workspace_permission(
            session, user.id, workspace.id, "can_edit_workspace"
        )

    @pytest.mark.asyncio
    async def test_operate_vs_edit_distinction(
        self, session: AsyncSession, workspace_factory, create_org_bundle
    ) -> None:
        """can_edit_workspace does NOT imply can_operate_workspace."""
        user = await _make_user(session)
        workspace = await workspace_factory()
        await create_org_bundle(
            user.id,
            atoms=("can_view_workspace", "can_edit_workspace"),
            workspace=workspace,
        )

        await require_workspace_permission(
            session, user.id, workspace.id, "can_edit_workspace"
        )
        with pytest.raises(ForbiddenError):
            await require_workspace_permission(
                session, user.id, workspace.id, "can_operate_workspace"
            )

    @pytest.mark.asyncio
    async def test_super_admin_bypass(
        self, session: AsyncSession, workspace_factory
    ) -> None:
        user = await _make_user(session, super_admin=True)
        workspace = await workspace_factory()
        await require_workspace_permission(
            session, user.id, workspace.id, "can_operate_workspace"
        )

    @pytest.mark.asyncio
    async def test_x_organization_id_mismatch_rejected(
        self, session: AsyncSession, workspace_factory, create_org_bundle
    ) -> None:
        user = await _make_user(session)
        workspace = await workspace_factory()
        await create_org_bundle(user.id, atoms=("can_view_workspace",), workspace=workspace)

        with pytest.raises(ForbiddenError) as exc:
            await require_workspace_permission(
                session,
                user.id,
                workspace.id,
                "can_view_workspace",
                x_organization_id=str(uuid.uuid4()),
            )
        assert exc.value.error_code == "organization.mismatch"


class TestPostOrganizations:
    @pytest.mark.asyncio
    async def test_zero_contract_user_can_create(
        self, client: TestClient, session: AsyncSession
    ) -> None:
        """B3: a logged-in user with 0 contracts may POST /organizations and
        receives the full org|ns|ws atom seed."""
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": "v40-creator",
                "email": "v40-creator@test.com",
                "password": "password123",
            },
        )
        assert resp.status_code == 201
        token = resp.json()["access_token"]

        slug = f"v40-world-{uuid.uuid4().hex[:6]}"
        create = client.post(
            "/api/v1/organizations",
            headers=_auth(token),
            json={"slug": slug, "name": "V40 World"},
        )
        assert create.status_code == 201, create.text

        # Creator holds the full atom seed via their OrgContract.
        from app.core.permissions import list_user_grant_slugs

        user_id = resp.json()["user"]["id"]
        slugs = await list_user_grant_slugs(session, user_id)
        assert "can_manage_organization" in slugs
        assert "can_manage_namespace" in slugs
        assert "can_operate_workspace" in slugs

    def test_existing_contract_user_can_create_another(
        self, client: TestClient
    ) -> None:
        """B3 locked: users who already hold contracts may create more worlds
        (no can_manage_organization gate in v4.0)."""
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": "v40-second",
                "email": "v40-second@test.com",
                "password": "password123",
            },
        )
        token = resp.json()["access_token"]
        for slug in (f"v40-a-{uuid.uuid4().hex[:4]}", f"v40-b-{uuid.uuid4().hex[:4]}"):
            create = client.post(
                "/api/v1/organizations",
                headers=_auth(token),
                json={"slug": slug, "name": slug},
            )
            assert create.status_code == 201, create.text

    def test_unauthenticated_rejected(self, client: TestClient) -> None:
        create = client.post(
            "/api/v1/organizations",
            json={"slug": f"v40-anon-{uuid.uuid4().hex[:4]}", "name": "anon"},
        )
        assert create.status_code == 401


class TestSystemScopeGuard:
    def test_create_system_scope_rejected(self, client: TestClient, auth_token: str) -> None:
        resp = client.post(
            "/api/v1/base-classes",
            headers=_auth(auth_token),
            json={
                "slug": f"v40-sys-{uuid.uuid4().hex[:6]}",
                "name": "System Attempt",
                "scope": "system",
            },
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "scope.system_create_forbidden"

    def test_update_builtin_preset_rejected(
        self, client: TestClient, auth_token: str
    ) -> None:
        """System-scoped builtin presets are read-only."""
        resp = client.get("/api/v1/base-classes/fox", headers=_auth(auth_token))
        assert resp.status_code == 200
        preset_id = resp.json()["id"]

        patch = client.patch(
            f"/api/v1/base-classes/{preset_id}",
            headers=_auth(auth_token),
            json={"description": "attempted edit"},
        )
        assert patch.status_code == 403
        assert patch.json()["error_code"] == "scope.system_readonly"

        delete = client.delete(
            f"/api/v1/base-classes/{preset_id}",
            headers=_auth(auth_token),
        )
        assert delete.status_code == 403


class TestOverlayJunction:
    @pytest.mark.asyncio
    async def test_agent_config_reads_junction(
        self, session: AsyncSession, entity_factory
    ) -> None:
        """resolve_instance_agent_config surfaces junction capabilities."""
        from app.core.capabilities import (
            attach_entity_capability,
            upsert_capability,
        )
        from app.core.overlay import resolve_instance_agent_config

        entity = await entity_factory()
        cap = await upsert_capability(
            session, name=f"v40-skill-{uuid.uuid4().hex[:6]}", cap_type="skill"
        )
        await attach_entity_capability(
            session, entity_id=entity.id, capability_id=cap.id
        )

        config = await resolve_instance_agent_config(session, entity)
        names = [c.get("name") for c in config["default_capabilities"]]
        assert cap.name in names


# Fixtures shared with the wider suite (registered user = super-admin).
@pytest.fixture
def auth_token(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": f"v40-admin-{uuid.uuid4().hex[:6]}",
            "email": f"v40-admin-{uuid.uuid4().hex[:6]}@test.com",
            "password": "password123",
        },
    )
    assert resp.status_code == 201
    return resp.json()["access_token"]
