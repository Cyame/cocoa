"""v4.1 X-Organization-Id membership gate (cross-org enumeration fix).

A caller must hold an active (non-deleted) OrganizationContract for the org
named in ``X-Organization-Id`` unless they are a platform super-admin.
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


class TestOrgHeaderMembershipGate:
    @pytest.mark.asyncio
    async def test_header_org_without_contract_forbidden(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(
            client,
            f"v41-gate-a-{uuid.uuid4().hex[:6]}",
            f"v41-gate-a-{uuid.uuid4().hex[:6]}@t.co",
        )
        member_token, member_id = _register(
            client,
            f"v41-gate-m-{uuid.uuid4().hex[:6]}",
            f"v41-gate-m-{uuid.uuid4().hex[:6]}@t.co",
        )
        assert member_id
        # Org exists but the member has no contract for it.
        bundle = await create_org_bundle(None)
        resp = client.get(
            "/api/v1/capability-market",
            headers={**_auth(member_token), "X-Organization-Id": bundle.org.id},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "organization.not_a_member"

    @pytest.mark.asyncio
    async def test_header_org_with_contract_succeeds(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(
            client,
            f"v41-gate-a-{uuid.uuid4().hex[:6]}",
            f"v41-gate-a-{uuid.uuid4().hex[:6]}@t.co",
        )
        member_token, member_id = _register(
            client,
            f"v41-gate-m-{uuid.uuid4().hex[:6]}",
            f"v41-gate-m-{uuid.uuid4().hex[:6]}@t.co",
        )
        bundle = await create_org_bundle(member_id, atoms=("can_view_workspace",))
        resp = client.get(
            "/api/v1/capability-market",
            headers={**_auth(member_token), "X-Organization-Id": bundle.org.id},
        )
        assert resp.status_code == 200
        assert "items" in resp.json()

    @pytest.mark.asyncio
    async def test_super_admin_bypasses_contract_check(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        admin_token, admin_id = _register(
            client,
            f"v41-gate-sa-{uuid.uuid4().hex[:6]}",
            f"v41-gate-sa-{uuid.uuid4().hex[:6]}@t.co",
        )
        assert admin_id
        # Org exists but the super-admin has no contract for it.
        bundle = await create_org_bundle(None)
        resp = client.get(
            "/api/v1/capability-market",
            headers={**_auth(admin_token), "X-Organization-Id": bundle.org.id},
        )
        assert resp.status_code == 200
        assert "items" in resp.json()

    @pytest.mark.asyncio
    async def test_nonexistent_org_in_header_not_found(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        _register(
            client,
            f"v41-gate-a-{uuid.uuid4().hex[:6]}",
            f"v41-gate-a-{uuid.uuid4().hex[:6]}@t.co",
        )
        member_token, member_id = _register(
            client,
            f"v41-gate-m-{uuid.uuid4().hex[:6]}",
            f"v41-gate-m-{uuid.uuid4().hex[:6]}@t.co",
        )
        await create_org_bundle(member_id, atoms=("can_view_workspace",))
        resp = client.get(
            "/api/v1/capability-market",
            headers={**_auth(member_token), "X-Organization-Id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "organization.not_found"
