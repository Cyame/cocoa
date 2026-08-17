"""v4.0 audit-fix gates — create_namespace and create_entity authorization.

Regression tests for the remaining Metis HIGH findings: any authenticated
user could create namespaces / entities anywhere.

- ``POST /namespaces`` now requires ``can_manage_namespace`` on the target
  organization (org-level atom).
- ``POST /entities`` now requires ``can_manage_namespace`` on the target
  namespace (namespace-level atom; there is no ``can_manage_entity`` atom).

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


class TestCreateNamespaceGate:
    @pytest.mark.asyncio
    async def test_member_cannot_create_namespace_without_grant(
        self, client: TestClient, session: AsyncSession, namespace_factory
    ) -> None:
        _register(client, f"audit-a-{uuid.uuid4().hex[:6]}", f"audit-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, _ = _register(
            client, f"audit-m-{uuid.uuid4().hex[:6]}", f"audit-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        # Ensure the default Organization exists for _resolve_org_id; the
        # factory only flushes, so commit for the API client's separate
        # connection.
        await namespace_factory(slug=f"audit-ns-{uuid.uuid4().hex[:6]}")
        await session.commit()

        resp = client.post(
            "/api/v1/namespaces",
            headers=_auth(member_token),
            json={"slug": f"audit-ns-{uuid.uuid4().hex[:6]}", "name": "Audit"},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

    @pytest.mark.asyncio
    async def test_member_with_can_manage_namespace_can_create(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(client, f"audit-a-{uuid.uuid4().hex[:6]}", f"audit-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"audit-m-{uuid.uuid4().hex[:6]}", f"audit-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle = await create_org_bundle(
            member_id, atoms=("can_manage_namespace",)
        )

        resp = client.post(
            "/api/v1/namespaces",
            headers=_auth(member_token),
            json={
                "slug": f"audit-ns-{uuid.uuid4().hex[:6]}",
                "name": "Audit",
                "org_id": bundle.org.id,
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["org_id"] == bundle.org.id

    @pytest.mark.asyncio
    async def test_admin_can_create_namespace(
        self, client: TestClient, session: AsyncSession, namespace_factory
    ) -> None:
        """Super-admin bypass still works (regression guard)."""
        admin_token, _ = _register(
            client, f"audit-a-{uuid.uuid4().hex[:6]}", f"audit-a-{uuid.uuid4().hex[:6]}@t.co"
        )
        await namespace_factory(slug=f"audit-ns-{uuid.uuid4().hex[:6]}")
        await session.commit()

        resp = client.post(
            "/api/v1/namespaces",
            headers=_auth(admin_token),
            json={"slug": f"audit-ns-{uuid.uuid4().hex[:6]}", "name": "Audit"},
        )
        assert resp.status_code == 201, resp.text


class TestCreateEntityGate:
    @pytest.mark.asyncio
    async def test_member_cannot_create_entity_without_grant(
        self, client: TestClient, session: AsyncSession, namespace_factory
    ) -> None:
        _register(client, f"audit-a-{uuid.uuid4().hex[:6]}", f"audit-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, _ = _register(
            client, f"audit-m-{uuid.uuid4().hex[:6]}", f"audit-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"audit-ns-{uuid.uuid4().hex[:6]}")
        await session.commit()

        resp = client.post(
            "/api/v1/entities",
            headers=_auth(member_token),
            json={
                "slug": f"audit-emp-{uuid.uuid4().hex[:6]}",
                "name": "Audit",
                "namespace_id": ns.id,
            },
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

    @pytest.mark.asyncio
    async def test_member_with_can_manage_namespace_can_create(
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
            "/api/v1/entities",
            headers=_auth(member_token),
            json={
                "slug": f"audit-emp-{uuid.uuid4().hex[:6]}",
                "name": "Audit",
                "namespace_id": ns.id,
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["namespace_id"] == ns.id

    @pytest.mark.asyncio
    async def test_admin_can_create_entity(
        self, client: TestClient, session: AsyncSession, namespace_factory
    ) -> None:
        """Super-admin bypass still works (regression guard)."""
        admin_token, _ = _register(
            client, f"audit-a-{uuid.uuid4().hex[:6]}", f"audit-a-{uuid.uuid4().hex[:6]}@t.co"
        )
        ns = await namespace_factory(slug=f"audit-ns-{uuid.uuid4().hex[:6]}")
        await session.commit()

        resp = client.post(
            "/api/v1/entities",
            headers=_auth(admin_token),
            json={
                "slug": f"audit-emp-{uuid.uuid4().hex[:6]}",
                "name": "Audit",
                "namespace_id": ns.id,
            },
        )
        assert resp.status_code == 201, resp.text
