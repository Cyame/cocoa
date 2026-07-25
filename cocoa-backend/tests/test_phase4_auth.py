"""Integration tests for P4 auth endpoints — register, login, JWT, protected routes.

Uses the ``client`` fixture (from conftest.py) which handles lifespan + registry
loading.  Each test runs against its own cloned database.
"""

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def auth_token(client: TestClient) -> str:
    """Register and login a throwaway user, return access token."""
    client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "email": "test@test.com",
        "password": "password123",
    })
    resp = client.post("/api/v1/auth/login", json={
        "username": "testuser",
        "password": "password123",
    })
    return resp.json()["access_token"]


class TestAuthRegister:
    """POST /api/v1/auth/register — user creation + JWT issuance."""

    def test_register_returns_jwt(self, client: TestClient) -> None:
        """Register a new user and verify 201 + access_token in response."""
        response = client.post("/api/v1/auth/register", json={
            "username": "alice",
            "email": "alice@test.com",
            "password": "securepass1",
        })
        assert response.status_code == 201
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert len(body["access_token"]) > 0

    def test_register_duplicate_username(self, client: TestClient) -> None:
        """Register the same username twice — second attempt returns 409."""
        payload = {
            "username": "bob",
            "email": "bob@test.com",
            "password": "securepass1",
        }
        resp1 = client.post("/api/v1/auth/register", json=payload)
        assert resp1.status_code == 201

        resp2 = client.post("/api/v1/auth/register", json=payload)
        assert resp2.status_code == 409
        body = resp2.json()
        assert body["error_code"] == "auth.username_taken"


class TestAuthLogin:
    """POST /api/v1/auth/login — credential verification + JWT issuance."""

    def test_login_returns_jwt(self, client: TestClient) -> None:
        """Login with correct credentials returns 200 + access_token."""
        client.post("/api/v1/auth/register", json={
            "username": "carol",
            "email": "carol@test.com",
            "password": "securepass1",
        })
        response = client.post("/api/v1/auth/login", json={
            "username": "carol",
            "password": "securepass1",
        })
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_login_wrong_password(self, client: TestClient) -> None:
        """Login with wrong password returns 401 + auth.invalid_credentials."""
        client.post("/api/v1/auth/register", json={
            "username": "dave",
            "email": "dave@test.com",
            "password": "securepass1",
        })
        response = client.post("/api/v1/auth/login", json={
            "username": "dave",
            "password": "wrongpassword",
        })
        assert response.status_code == 401
        body = response.json()
        assert body["error_code"] == "auth.invalid_credentials"


class TestAuthProtected:
    """Endpoints that require authentication."""

    def test_protected_endpoint_requires_auth(self, client: TestClient) -> None:
        """GET /api/v1/employees without token returns 401."""
        response = client.get("/api/v1/employees")
        assert response.status_code == 401
        body = response.json()
        assert body["error_code"] == "auth.token_missing"
