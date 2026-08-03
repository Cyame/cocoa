"""v4-3 D14+H3: GET /api/v1/users/search — org member-manager user search.

Permission: ``can_manage_org_members`` on the current org (resolved via the
``X-Organization-Id`` header + ``resolve_current_org_id``) or super-admin;
no valid org context and not super-admin → 403. Responses are slim
(id/username/email/nickname) — no password_hash / identity / gene data.

Also pins the untouched super-admin-only gate on the existing GET /users.
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
        json={"username": username, "email": email, "password": "password123"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["id"]


def _create_user(client: TestClient, sa_token: str, username: str, email: str) -> None:
    resp = client.post(
        "/api/v1/users",
        headers=_auth(sa_token),
        json={"username": username, "email": email, "identity": "member"},
    )
    assert resp.status_code == 201, resp.text


async def _env(
    client: TestClient,
    create_org_bundle,
    *,
    targets: list[tuple[str, str]] | None = None,
    mgr_atoms: tuple[str, ...] = ("can_manage_org_members",),
) -> dict:
    """Super-admin + org manager (default org) + target users, created in order."""
    sa_token, _ = _register(
        client,
        f"v43-sa-{uuid.uuid4().hex[:6]}",
        f"sa-{uuid.uuid4().hex[:6]}@t.co",
    )
    target_users = targets or [
        ("alice-dev", "alice@example.com"),
        ("bob-dev", "bob@example.com"),
        ("carol-dev", "carol@example.com"),
    ]
    mgr_token: str | None = None
    mgr_id: str | None = None
    org_id: str | None = None
    if mgr_atoms is not None:
        mgr_token, mgr_id = _register(
            client,
            f"v43-mgr-{uuid.uuid4().hex[:6]}",
            f"mgr-{uuid.uuid4().hex[:6]}@t.co",
        )
        bundle = await create_org_bundle(mgr_id, atoms=mgr_atoms)
        org_id = bundle.org.id
    for username, email in target_users:
        _create_user(client, sa_token, username, email)
    return {
        "sa_token": sa_token,
        "mgr_token": mgr_token,
        "mgr_id": mgr_id,
        "org_id": org_id,
        "targets": target_users,
    }


def _mgr_headers(env: dict) -> dict[str, str]:
    return {**_auth(env["mgr_token"]), "X-Organization-Id": env["org_id"]}


class TestBaselineGetUsersGate:
    """Pin the existing GET /users super-admin gate (unchanged by v4-3)."""

    def test_non_super_admin_cannot_list_users(self, client: TestClient) -> None:
        # First registered user is auto-promoted to super-admin (P14b-onboard);
        # a later user is a plain member and must be rejected by GET /users.
        _register(
            client,
            f"v43-base-sa-{uuid.uuid4().hex[:6]}",
            f"base-sa-{uuid.uuid4().hex[:6]}@t.co",
        )
        token, _ = _register(
            client,
            f"v43-base-m-{uuid.uuid4().hex[:6]}",
            f"base-{uuid.uuid4().hex[:6]}@t.co",
        )
        resp = client.get("/api/v1/users", headers=_auth(token))
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "auth.super_admin_required"

    def test_super_admin_can_list_users(self, client: TestClient) -> None:
        token, _ = _register(
            client,
            f"v43-base-sa-{uuid.uuid4().hex[:6]}",
            f"base-sa-{uuid.uuid4().hex[:6]}@t.co",
        )
        resp = client.get("/api/v1/users", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1


class TestSearchPermission:
    @pytest.mark.asyncio
    async def test_can_manage_org_members_holder_can_search(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        env = await _env(client, create_org_bundle)
        resp = client.get(
            "/api/v1/users/search",
            headers=_mgr_headers(env),
            params={"q": "ali"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert [u["username"] for u in body["items"]] == ["alice-dev"]

    @pytest.mark.asyncio
    async def test_single_contract_auto_resolves_org_without_header(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        env = await _env(client, create_org_bundle)
        resp = client.get(
            "/api/v1/users/search",
            headers=_auth(env["mgr_token"]),
            params={"q": "bob"},
        )
        assert resp.status_code == 200, resp.text
        assert [u["username"] for u in resp.json()["items"]] == ["bob-dev"]

    @pytest.mark.asyncio
    async def test_view_only_atom_forbidden(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        env = await _env(client, create_org_bundle, mgr_atoms=("can_view_workspace",))
        resp = client.get(
            "/api/v1/users/search",
            headers=_mgr_headers(env),
            params={"q": "ali"},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "permission.denied"

    @pytest.mark.asyncio
    async def test_no_org_context_forbidden(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        # First registered user is auto-promoted to super-admin, which would
        # bypass the gate — register one first, then the zero-contract user.
        _register(
            client,
            f"v43-sa-{uuid.uuid4().hex[:6]}",
            f"sa-{uuid.uuid4().hex[:6]}@t.co",
        )
        token, _ = _register(
            client,
            f"v43-none-{uuid.uuid4().hex[:6]}",
            f"none-{uuid.uuid4().hex[:6]}@t.co",
        )
        resp = client.get(
            "/api/v1/users/search", headers=_auth(token), params={"q": "ali"}
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "organization.context_required"

    @pytest.mark.asyncio
    async def test_different_org_forbidden(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        from app.models.organization import Organization

        sa_token, _ = _register(
            client,
            f"v43-sa-{uuid.uuid4().hex[:6]}",
            f"sa-{uuid.uuid4().hex[:6]}@t.co",
        )
        _create_user(client, sa_token, "alice-dev", "alice@example.com")
        mgr_token, mgr_id = _register(
            client,
            f"v43-mgr-{uuid.uuid4().hex[:6]}",
            f"mgr-{uuid.uuid4().hex[:6]}@t.co",
        )
        default_bundle = await create_org_bundle(None)
        other = Organization(slug=f"orgb-{uuid.uuid4().hex[:8]}", name="Other Org")
        session.add(other)
        await session.flush()
        # Manager's only contract is in a DIFFERENT org.
        await create_org_bundle(
            mgr_id, atoms=("can_manage_org_members",), organization=other
        )
        resp = client.get(
            "/api/v1/users/search",
            headers={**_auth(mgr_token), "X-Organization-Id": default_bundle.org.id},
            params={"q": "ali"},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "organization.not_a_member"

    @pytest.mark.asyncio
    async def test_super_admin_bypasses_org_requirement(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        env = await _env(client, create_org_bundle)
        # No org context at all — super-admin bypasses the gate.
        resp = client.get(
            "/api/v1/users/search",
            headers=_auth(env["sa_token"]),
            params={"q": "alice"},
        )
        assert resp.status_code == 200, resp.text
        assert [u["username"] for u in resp.json()["items"]] == ["alice-dev"]


class TestSearchSemantics:
    @pytest.mark.asyncio
    async def test_prefix_search_by_email(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        env = await _env(client, create_org_bundle)
        resp = client.get(
            "/api/v1/users/search",
            headers=_mgr_headers(env),
            params={"q": "bob@exa"},
        )
        assert resp.status_code == 200, resp.text
        assert [u["username"] for u in resp.json()["items"]] == ["bob-dev"]

    @pytest.mark.asyncio
    async def test_case_insensitive_prefix(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        env = await _env(client, create_org_bundle)
        resp = client.get(
            "/api/v1/users/search",
            headers=_mgr_headers(env),
            params={"q": "ALICE"},
        )
        assert resp.status_code == 200, resp.text
        assert [u["username"] for u in resp.json()["items"]] == ["alice-dev"]

    @pytest.mark.asyncio
    async def test_missing_or_empty_q_returns_recent_users(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        env = await _env(client, create_org_bundle)
        headers = _mgr_headers(env)
        resp = client.get("/api/v1/users/search", headers=headers, params={"q": ""})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] >= 3
        # carol-dev was created last → most recent.
        assert body["items"][0]["username"] == "carol-dev"
        # Missing q behaves the same as empty q.
        resp2 = client.get("/api/v1/users/search", headers=headers)
        assert resp2.status_code == 200
        assert resp2.json()["items"][0]["username"] == "carol-dev"

    @pytest.mark.asyncio
    async def test_wildcards_treated_literally(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        env = await _env(
            client,
            create_org_bundle,
            targets=[
                ("alpha", "alpha@example.com"),
                ("beta", "beta@example.com"),
                ("gamma", "gamma@example.com"),
            ],
        )
        headers = _mgr_headers(env)
        for needle in ("a%", "al_ha", "_", "%"):
            resp = client.get(
                "/api/v1/users/search", headers=headers, params={"q": needle}
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["total"] == 0, (
                f"q={needle!r} must be escaped (no literal match expected)"
            )
        # Plain prefix still works after escaping.
        resp = client.get("/api/v1/users/search", headers=headers, params={"q": "a"})
        assert resp.status_code == 200
        assert [u["username"] for u in resp.json()["items"]] == ["alpha"]

    @pytest.mark.asyncio
    async def test_limit_capped_and_default(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        targets = [
            (f"zz-lim-{i:02d}", f"zz{i:02d}@example.com") for i in range(1, 13)
        ]
        env = await _env(client, create_org_bundle, targets=targets)
        headers = _mgr_headers(env)
        resp = client.get(
            "/api/v1/users/search", headers=headers, params={"q": "zz-lim"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 12
        assert len(body["items"]) == 10  # default limit
        assert body["limit"] == 10
        resp2 = client.get(
            "/api/v1/users/search",
            headers=headers,
            params={"q": "zz-lim", "limit": 9999},
        )
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert body2["limit"] == 50  # capped
        assert len(body2["items"]) == 12
        assert body2["total"] == 12

    @pytest.mark.asyncio
    async def test_response_is_slim_no_sensitive_fields(
        self, client: TestClient, session: AsyncSession, create_org_bundle
    ) -> None:
        env = await _env(client, create_org_bundle)
        resp = client.get(
            "/api/v1/users/search",
            headers=_mgr_headers(env),
            params={"q": "ali"},
        )
        assert resp.status_code == 200, resp.text
        item = resp.json()["items"][0]
        assert set(item.keys()) == {"id", "username", "email", "nickname"}
        assert item["id"]
        assert item["username"] == "alice-dev"
        assert item["email"] == "alice@example.com"
        assert "password_hash" not in item
        assert "is_super_admin" not in item
        assert "identity" not in item
        assert "extra_genes" not in item
