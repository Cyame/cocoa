"""v4-3 lane 5 — GET /api/v1/auth/me org_identity (plan B4 / H7).

Behavior contract:
- No ``X-Organization-Id`` header: existing response shape; ``org_identity``
  stays null.
- Header + valid OrganizationContract: ``org_identity`` carries org-level
  atom slugs (``list_grant_slugs``) + a display-only ``display_label``
  (owner / operator / editor / viewer heuristic).
- Header + invalid org / non-member / malformed id: ``org_identity`` null,
  status 200 — /auth/me is a status endpoint, never a 4xx.
- Super-admin with header: full atom catalog.
"""

from __future__ import annotations

import uuid

import pytest
from starlette.testclient import TestClient

from app.core.gene_atoms import ATOM_CATALOG


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, tag: str) -> dict:
    """Register a user via the API; returns the full JSON body."""
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": f"v43-{tag}-{uuid.uuid4().hex[:6]}",
            "email": f"v43-{tag}-{uuid.uuid4().hex[:6]}@test.com",
            "password": "password123",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestMeBaseline:
    """No X-Organization-Id header — existing /me response must not change."""

    def test_me_pins_existing_shape(self, client: TestClient) -> None:
        """Pins CURRENT response fields (regression net for B4/H7 compat)."""
        body = _register(client, "base")
        me = client.get("/api/v1/auth/me", headers=_auth(body["access_token"]))
        assert me.status_code == 200
        data = me.json()
        assert data["id"] == body["user"]["id"]
        assert data["username"].startswith("v43-base-")
        assert data["email"].endswith("@test.com")
        assert data["is_super_admin"] is True  # first registered user
        assert data["identity"] == "system"
        assert data["locked_gene_slugs"] == []
        assert isinstance(data["extra_gene_slugs"], list)

    def test_me_no_header_org_identity_null(self, client: TestClient) -> None:
        """Without the header org_identity must be present and null."""
        body = _register(client, "plain")
        me = client.get("/api/v1/auth/me", headers=_auth(body["access_token"]))
        assert me.status_code == 200
        data = me.json()
        assert "org_identity" in data
        assert data["org_identity"] is None


class TestMeOrgIdentity:
    """Header present + valid OrganizationContract → org_identity payload."""

    @pytest.mark.asyncio
    async def test_member_viewer(self, client, session, create_org_bundle) -> None:
        _register(client, "creator")  # first user → super admin
        member = _register(client, "member")  # normal user
        bundle = await create_org_bundle(
            member["user"]["id"], atoms=("can_view_workspace",)
        )

        me = client.get(
            "/api/v1/auth/me",
            headers={**_auth(member["access_token"]), "X-Organization-Id": bundle.org.id},
        )
        assert me.status_code == 200
        identity = me.json()["org_identity"]
        assert identity["organization_id"] == bundle.org.id
        assert identity["atoms"] == ["can_view_workspace"]
        assert identity["display_label"] == "viewer"

    @pytest.mark.asyncio
    async def test_member_editor(self, client, session, create_org_bundle) -> None:
        _register(client, "creator")
        member = _register(client, "member")
        bundle = await create_org_bundle(
            member["user"]["id"],
            atoms=("can_view_workspace", "can_edit_workspace"),
        )

        me = client.get(
            "/api/v1/auth/me",
            headers={**_auth(member["access_token"]), "X-Organization-Id": bundle.org.id},
        )
        assert me.status_code == 200
        identity = me.json()["org_identity"]
        assert identity["atoms"] == ["can_edit_workspace", "can_view_workspace"]
        assert identity["display_label"] == "editor"

    @pytest.mark.asyncio
    async def test_member_operator(self, client, session, create_org_bundle) -> None:
        _register(client, "creator")
        member = _register(client, "member")
        bundle = await create_org_bundle(
            member["user"]["id"],
            atoms=("can_view_workspace", "can_edit_workspace", "can_operate_workspace"),
        )

        me = client.get(
            "/api/v1/auth/me",
            headers={**_auth(member["access_token"]), "X-Organization-Id": bundle.org.id},
        )
        assert me.status_code == 200
        identity = me.json()["org_identity"]
        assert identity["atoms"] == [
            "can_edit_workspace",
            "can_operate_workspace",
            "can_view_workspace",
        ]
        assert identity["display_label"] == "operator"

    @pytest.mark.asyncio
    async def test_member_owner(self, client, session, create_org_bundle) -> None:
        _register(client, "creator")
        member = _register(client, "member")
        bundle = await create_org_bundle(
            member["user"]["id"],
            atoms=("can_manage_organization", "can_view_workspace"),
        )

        me = client.get(
            "/api/v1/auth/me",
            headers={**_auth(member["access_token"]), "X-Organization-Id": bundle.org.id},
        )
        assert me.status_code == 200
        identity = me.json()["org_identity"]
        assert identity["atoms"] == ["can_manage_organization", "can_view_workspace"]
        assert identity["display_label"] == "owner"

    @pytest.mark.asyncio
    async def test_super_admin_full_atoms(self, client, session, create_org_bundle) -> None:
        """Super-admin bypasses membership; /me reports the full catalog."""
        body = _register(client, "root")  # first user → super admin
        assert body["user"]["is_super_admin"] is True
        bundle = await create_org_bundle()  # default org, no contract needed

        me = client.get(
            "/api/v1/auth/me",
            headers={**_auth(body["access_token"]), "X-Organization-Id": bundle.org.id},
        )
        assert me.status_code == 200
        identity = me.json()["org_identity"]
        assert identity["organization_id"] == bundle.org.id
        assert identity["atoms"] == sorted(ATOM_CATALOG)
        assert identity["display_label"] == "owner"

    @pytest.mark.asyncio
    async def test_unknown_org_header_returns_null(self, client, session) -> None:
        """Nonexistent org id in header → org_identity null, not 404/500."""
        body = _register(client, "ghost")
        me = client.get(
            "/api/v1/auth/me",
            headers={**_auth(body["access_token"]), "X-Organization-Id": str(uuid.uuid4())},
        )
        assert me.status_code == 200
        assert me.json()["org_identity"] is None

    @pytest.mark.asyncio
    async def test_malformed_org_header_returns_null(self, client, session) -> None:
        """Non-uuid header value → org_identity null, never a 500."""
        body = _register(client, "mal")
        me = client.get(
            "/api/v1/auth/me",
            headers={**_auth(body["access_token"]), "X-Organization-Id": "not-a-uuid"},
        )
        assert me.status_code == 200
        assert me.json()["org_identity"] is None

    @pytest.mark.asyncio
    async def test_non_member_header_returns_null(self, client, session, create_org_bundle) -> None:
        """Non-member must NOT leak atoms — org_identity null (permission_bypass)."""
        _register(client, "creator")
        member = _register(client, "member")
        outsider = _register(client, "outsider")
        bundle = await create_org_bundle(
            member["user"]["id"],
            atoms=("can_edit_workspace", "can_manage_organization"),
        )

        me = client.get(
            "/api/v1/auth/me",
            headers={**_auth(outsider["access_token"]), "X-Organization-Id": bundle.org.id},
        )
        assert me.status_code == 200
        data = me.json()
        assert data["org_identity"] is None
        assert "atoms" not in data
