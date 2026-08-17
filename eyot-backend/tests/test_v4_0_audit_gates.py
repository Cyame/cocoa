"""v4.0 audit-fix gates — non-super-admin rejection paths.

Regression tests for the review findings that the namespace-contract CRUD and
workspace creation were reachable by any authenticated user:

- ``POST/PATCH/DELETE /namespaces/{id}/contracts`` now require
  ``can_manage_namespace``; ``GET .../contracts`` requires
  ``can_view_workspace``.
- ``POST /workspaces`` now requires ``can_manage_workspace`` on the target
  namespace (org- or namespace-grant).

These tests exercise the *non-super-admin* branches the wider suite misses
(every other API test registers the first user, who auto-promotes to
super-admin).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, username: str, email: str) -> tuple[str, str]:
    """Register; returns (token, user_id) straight from the 201 response.

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


class TestNamespaceContractGates:
    @pytest.mark.asyncio
    async def test_member_cannot_create_contract_without_grant(
        self, client: TestClient, session: AsyncSession, namespace_factory
    ) -> None:
        _register(client, f"audit-a-{uuid.uuid4().hex[:6]}", f"audit-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"audit-m-{uuid.uuid4().hex[:6]}", f"audit-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"audit-ns-{uuid.uuid4().hex[:6]}")
        # namespace_factory only flushes; commit so the API client's separate
        # connection can see the namespace.
        await session.commit()

        resp = client.post(
            f"/api/v1/namespaces/{ns.id}/contracts",
            headers=_auth(member_token),
            json={
                "user_id": member_id,
                "gene_slugs": ["can_operate_workspace"],
            },
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

    @pytest.mark.asyncio
    async def test_member_cannot_list_contracts_without_view(
        self, client: TestClient, session: AsyncSession, namespace_factory
    ) -> None:
        _register(client, f"audit-a-{uuid.uuid4().hex[:6]}", f"audit-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, _ = _register(
            client, f"audit-m-{uuid.uuid4().hex[:6]}", f"audit-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"audit-ns-{uuid.uuid4().hex[:6]}")
        await session.commit()

        resp = client.get(
            f"/api/v1/namespaces/{ns.id}/contracts", headers=_auth(member_token)
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

    @pytest.mark.asyncio
    async def test_member_with_can_manage_namespace_can_create_contract(
        self, client: TestClient, session: AsyncSession, namespace_factory, create_org_bundle
    ) -> None:
        _register(client, f"audit-a-{uuid.uuid4().hex[:6]}", f"audit-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"audit-m-{uuid.uuid4().hex[:6]}", f"audit-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"audit-ns-{uuid.uuid4().hex[:6]}")
        await create_org_bundle(
            member_id, atoms=("can_manage_namespace",), namespace=ns
        )

        resp = client.post(
            f"/api/v1/namespaces/{ns.id}/contracts",
            headers=_auth(member_token),
            json={
                "user_id": member_id,
                "gene_slugs": ["can_view_workspace", "can_edit_workspace"],
            },
        )
        assert resp.status_code == 201, resp.text
        slugs = {g["slug"] for g in resp.json()["genes"]}
        assert {"can_view_workspace", "can_edit_workspace"} <= slugs

    @pytest.mark.asyncio
    async def test_admin_can_create_and_update_contract(
        self, client: TestClient, session: AsyncSession, namespace_factory
    ) -> None:
        """Super-admin bypass still works (regression guard)."""
        admin_token, admin_id = _register(
            client, f"audit-a-{uuid.uuid4().hex[:6]}", f"audit-a-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"audit-ns-{uuid.uuid4().hex[:6]}")
        await session.commit()

        created = client.post(
            f"/api/v1/namespaces/{ns.id}/contracts",
            headers=_auth(admin_token),
            json={"user_id": admin_id, "gene_slugs": ["can_view_workspace"]},
        )
        assert created.status_code == 201, created.text
        contract_id = created.json()["id"]

        updated = client.patch(
            f"/api/v1/namespaces/{ns.id}/contracts/{contract_id}",
            headers=_auth(admin_token),
            json={"gene_slugs": ["can_view_workspace", "can_edit_workspace"]},
        )
        assert updated.status_code == 200, updated.text


class TestCreateWorkspaceGate:
    @pytest.mark.asyncio
    async def test_member_cannot_create_workspace_without_grant(
        self, client: TestClient, session: AsyncSession, namespace_factory
    ) -> None:
        _register(client, f"audit-a-{uuid.uuid4().hex[:6]}", f"audit-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, _ = _register(
            client, f"audit-m-{uuid.uuid4().hex[:6]}", f"audit-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"audit-ns-{uuid.uuid4().hex[:6]}")
        await session.commit()

        resp = client.post(
            "/api/v1/workspaces",
            headers=_auth(member_token),
            json={"slug": f"audit-ws-{uuid.uuid4().hex[:6]}", "name": "Audit", "namespace_id": ns.id},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

    @pytest.mark.asyncio
    async def test_member_with_can_manage_workspace_can_create(
        self, client: TestClient, session: AsyncSession, namespace_factory, create_org_bundle
    ) -> None:
        _register(client, f"audit-a-{uuid.uuid4().hex[:6]}", f"audit-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"audit-m-{uuid.uuid4().hex[:6]}", f"audit-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"audit-ns-{uuid.uuid4().hex[:6]}")
        await create_org_bundle(
            member_id, atoms=("can_manage_workspace",), namespace=ns
        )

        resp = client.post(
            "/api/v1/workspaces",
            headers=_auth(member_token),
            json={"slug": f"audit-ws-{uuid.uuid4().hex[:6]}", "name": "Audit", "namespace_id": ns.id},
        )
        assert resp.status_code == 201, resp.text

    @pytest.mark.asyncio
    async def test_admin_can_create_workspace(
        self, client: TestClient, session: AsyncSession, namespace_factory
    ) -> None:
        admin_token, _ = _register(
            client, f"audit-a-{uuid.uuid4().hex[:6]}", f"audit-a-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"audit-ns-{uuid.uuid4().hex[:6]}")
        await session.commit()

        resp = client.post(
            "/api/v1/workspaces",
            headers=_auth(admin_token),
            json={"slug": f"audit-ws-{uuid.uuid4().hex[:6]}", "name": "Audit", "namespace_id": ns.id},
        )
        assert resp.status_code == 201, resp.text
