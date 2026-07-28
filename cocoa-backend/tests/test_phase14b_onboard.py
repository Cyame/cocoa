"""Integration tests for P14b-onboard — first-user auto super admin.

Covers decision D-perm-2026-07-28: the first user to register against an
empty user table is automatically promoted to ``is_super_admin=True`` so
an empty deployment can be booted without manual SQL. Subsequent
registrations default to ``is_super_admin=False``.

Each test runs against its own cloned database via the ``client`` fixture,
so user count starts at 0 and isolation is guaranteed.
"""

from starlette.testclient import TestClient

from app.core.config import settings
from app.core.security import decode_token


def _decode_admin_claim(client_response: dict) -> bool:
    """Decode the JWT in a register/login response and return its
    ``is_super_admin`` claim."""
    token = client_response["access_token"]
    payload = decode_token(token, settings.JWT_SECRET)
    return bool(payload["is_super_admin"])


class TestFirstUserSuperAdmin:
    """POST /api/v1/auth/register — first-user promotion."""

    def test_first_user_is_super_admin(self, client: TestClient) -> None:
        """Empty user table → first registration gets is_super_admin=True."""
        response = client.post("/api/v1/auth/register", json={
            "username": "firstuser",
            "email": "first@test.local",
            "password": "securepass1",
        })
        assert response.status_code == 201
        body = response.json()
        assert "access_token" in body
        # JWT carries the promotion immediately.
        assert _decode_admin_claim(body) is True

    def test_second_user_is_not_super_admin(self, client: TestClient) -> None:
        """Second registration against non-empty table → is_super_admin=False."""
        first = client.post("/api/v1/auth/register", json={
            "username": "alpha",
            "email": "alpha@test.local",
            "password": "securepass1",
        })
        assert first.status_code == 201
        assert _decode_admin_claim(first.json()) is True

        second = client.post("/api/v1/auth/register", json={
            "username": "beta",
            "email": "beta@test.local",
            "password": "securepass2",
        })
        assert second.status_code == 201
        # JWT carries the non-admin status for subsequent users.
        assert _decode_admin_claim(second.json()) is False

    def test_third_and_later_users_stay_non_admin(self, client: TestClient) -> None:
        """Promotion only fires once — users 3..N stay non-admin."""
        for i, name in enumerate(("u1", "u2", "u3", "u4")):
            resp = client.post("/api/v1/auth/register", json={
                "username": name,
                "email": f"{name}@test.local",
                "password": "securepass1",
            })
            assert resp.status_code == 201
            expected = i == 0
            assert _decode_admin_claim(resp.json()) is expected, (
                f"user {name} (index {i}) expected is_super_admin={expected}"
            )

    def test_first_user_admin_claim_survives_login(self, client: TestClient) -> None:
        """Login flow re-issues the JWT with the same admin claim from DB."""
        client.post("/api/v1/auth/register", json={
            "username": "promoted",
            "email": "promoted@test.local",
            "password": "securepass1",
        })
        login = client.post("/api/v1/auth/login", json={
            "username": "promoted",
            "password": "securepass1",
        })
        assert login.status_code == 200
        assert _decode_admin_claim(login.json()) is True

    def test_second_user_login_is_not_super_admin(self, client: TestClient) -> None:
        """Login flow for second user reflects the non-admin DB state."""
        client.post("/api/v1/auth/register", json={
            "username": "alpha",
            "email": "alpha@test.local",
            "password": "securepass1",
        })
        client.post("/api/v1/auth/register", json={
            "username": "beta",
            "email": "beta@test.local",
            "password": "securepass2",
        })
        login = client.post("/api/v1/auth/login", json={
            "username": "beta",
            "password": "securepass2",
        })
        assert login.status_code == 200
        assert _decode_admin_claim(login.json()) is False
