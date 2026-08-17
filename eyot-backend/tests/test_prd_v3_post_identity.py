"""PRD-v3-post identity pack + user admin API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def auth_token(client: TestClient) -> str:
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "v3post",
            "email": "v3post@test.com",
            "password": "password123",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "v3post", "password": "password123"},
    )
    return resp.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestIdentityAndUsers:
    def test_first_user_has_system_identity(
        self, client: TestClient, auth_token: str
    ) -> None:
        me = client.get("/api/v1/auth/me", headers=_h(auth_token))
        assert me.status_code == 200
        body = me.json()
        assert body["is_super_admin"] is True
        assert body["identity"] == "system"
        # v4.0: identity packs are gone — no locked gene rows.
        assert body["locked_gene_slugs"] == []

    def test_account_and_list_users(self, client: TestClient, auth_token: str) -> None:
        account = client.get("/api/v1/account", headers=_h(auth_token))
        assert account.status_code == 200
        assert account.json()["identity"] == "system"

        listing = client.get("/api/v1/users", headers=_h(auth_token))
        assert listing.status_code == 200
        assert listing.json()["total"] >= 1

    def test_create_user_with_member_identity(
        self, client: TestClient, auth_token: str
    ) -> None:
        created = client.post(
            "/api/v1/users",
            headers=_h(auth_token),
            json={
                "username": "member-alice",
                "email": "alice@example.com",
                "identity": "member",
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        # v4.0: non-system identities derive to None (flag is False).
        assert body["identity"] is None
        assert body["is_super_admin"] is False
        assert body["temporary_password"]
        assert body["locked_genes"] == []

        set_id = client.post(
            f"/api/v1/users/{body['id']}/identity",
            headers=_h(auth_token),
            json={"identity": "system"},
        )
        assert set_id.status_code == 200
        assert set_id.json()["identity"] == "system"
        assert set_id.json()["is_super_admin"] is True

        unset = client.post(
            f"/api/v1/users/{body['id']}/identity",
            headers=_h(auth_token),
            json={"identity": "member"},
        )
        assert unset.status_code == 200
        assert unset.json()["identity"] is None
        assert unset.json()["is_super_admin"] is False
