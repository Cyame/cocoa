"""v4.0 BLOCKER-1 — route-layer X-Organization-Id header enforcement.

Regression tests for the audit finding that ``require_workspace_permission``
accepted ``x_organization_id`` but no route ever read the ``X-Organization-Id``
header, so the org-consistency check never fired in production.

These tests exercise the *route layer* (the DB-level direct-call test in
``test_v4_0_auth_scope.py::test_x_organization_id_mismatch_rejected`` only
proves the pure function; this file proves the header is actually wired).

- Wrong ``X-Organization-Id`` header → 403 ``organization.mismatch``
- Correct header → 2xx (org matches)
- No header → 2xx (v4.0 transitional fallback to resolved org)
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient


def _auth(token: str, x_org: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if x_org is not None:
        headers["X-Organization-Id"] = x_org
    return headers


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


class TestXOrgHeaderRouteLayer:
    @pytest.mark.asyncio
    async def test_wrong_org_header_rejected(
        self, client: TestClient, session: AsyncSession, workspace_factory, create_org_bundle
    ) -> None:
        _register(client, f"audit-a-{uuid.uuid4().hex[:6]}", f"audit-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"audit-m-{uuid.uuid4().hex[:6]}", f"audit-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        ws = await workspace_factory()
        await create_org_bundle(member_id, atoms=("can_view_workspace",), workspace=ws)
        # workspace_factory only flushes; commit so the API client's separate
        # connection can see the workspace.
        await session.commit()

        resp = client.get(
            f"/api/v1/workspaces/{ws.id}/live-status",
            headers=_auth(member_token, x_org=str(uuid.uuid4())),
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "organization.mismatch"

    @pytest.mark.asyncio
    async def test_correct_org_header_allowed(
        self, client: TestClient, session: AsyncSession, workspace_factory, create_org_bundle
    ) -> None:
        _register(client, f"audit-a-{uuid.uuid4().hex[:6]}", f"audit-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"audit-m-{uuid.uuid4().hex[:6]}", f"audit-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        ws = await workspace_factory()
        bundle = await create_org_bundle(
            member_id, atoms=("can_view_workspace",), workspace=ws
        )
        await session.commit()

        resp = client.get(
            f"/api/v1/workspaces/{ws.id}/live-status",
            headers=_auth(member_token, x_org=bundle.org.id),
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_no_header_falls_back_to_resolved_org(
        self, client: TestClient, session: AsyncSession, workspace_factory, create_org_bundle
    ) -> None:
        _register(client, f"audit-a-{uuid.uuid4().hex[:6]}", f"audit-a-{uuid.uuid4().hex[:6]}@t.co")
        member_token, member_id = _register(
            client, f"audit-m-{uuid.uuid4().hex[:6]}", f"audit-m-{uuid.uuid4().hex[:6]}@t.co"
        )
        ws = await workspace_factory()
        await create_org_bundle(member_id, atoms=("can_view_workspace",), workspace=ws)
        await session.commit()

        # No X-Organization-Id header — transitional fallback must succeed.
        resp = client.get(
            f"/api/v1/workspaces/{ws.id}/live-status",
            headers=_auth(member_token),
        )
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_super_admin_bypass_with_wrong_header(
        self, client: TestClient, session: AsyncSession, workspace_factory
    ) -> None:
        """Super-admins bypass atom checks entirely (platform exception)."""
        admin_token, _ = _register(
            client, f"audit-a-{uuid.uuid4().hex[:6]}", f"audit-a-{uuid.uuid4().hex[:6]}@t.co"
        )
        ws = await workspace_factory()
        await session.commit()

        resp = client.get(
            f"/api/v1/workspaces/{ws.id}/live-status",
            headers=_auth(admin_token, x_org=str(uuid.uuid4())),
        )
        assert resp.status_code == 200, resp.text
