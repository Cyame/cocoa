"""Integration tests for P4 CRUD endpoints — entity-presets, entities, workspaces.

All HTTP tests use the ``client`` fixture (from conftest.py) which handles
lifespan + registry loading.  The ``auth_token`` fixture registers+logs in a
throwaway user per test.  Each test runs against its own cloned database.
"""

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def auth_token(client: TestClient) -> str:
    """Register and login a throwaway user, return access token."""
    client.post("/api/v1/auth/register", json={
        "username": "crudtest",
        "email": "crudtest@test.com",
        "password": "password123",
    })
    resp = client.post("/api/v1/auth/login", json={
        "username": "crudtest",
        "password": "password123",
    })
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# =========================================================================
# BaseClass CRUD
# =========================================================================


class TestBaseClassCrud:
    """CRUD for /api/v1/base-classes."""

    def test_list_base_classes(self, client: TestClient, auth_token: str) -> None:
        """GET /api/v1/base-classes returns the 11 public 神职 (zong-jian hidden)."""
        response = client.get(
            "/api/v1/base-classes",
            headers=_auth_headers(auth_token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 11
        slugs = {item["slug"] for item in body["items"]}
        for expected in (
            "mi-shi",
            "huan-ling",
            "an-xing",
            "an-ying",
            "zhu-jin",
            "ling-shi",
            "heng-pan",
            "you-hun",
            "qian-zhi",
            "bai-tong",
            "jiu-ri",
        ):
            assert expected in slugs, f"Built-in preset {expected} missing"
        assert "zong-jian" not in slugs

    def test_create_base_class(self, client: TestClient, auth_token: str) -> None:
        """POST /api/v1/base-classes returns 201 with the new preset."""
        response = client.post(
            "/api/v1/base-classes",
            headers=_auth_headers(auth_token),
            json={
                "slug": "my-custom",
                "name": "My Custom Preset",
                "version": "1.0",
                "manifest": {"model": "gpt-4"},
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["slug"] == "my-custom"
        assert body["name"] == "My Custom Preset"
        assert "id" in body

    def test_create_base_class_duplicate_slug(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """Creating a preset with an existing slug returns 409."""
        payload = {
            "slug": "dup-slug",
            "name": "Original",
        }
        resp1 = client.post(
            "/api/v1/base-classes",
            headers=_auth_headers(auth_token),
            json=payload,
        )
        assert resp1.status_code == 201

        resp2 = client.post(
            "/api/v1/base-classes",
            headers=_auth_headers(auth_token),
            json=payload,
        )
        assert resp2.status_code == 409
        assert resp2.json()["error_code"] == "base_class.slug_taken"

    def test_delete_base_class_soft_delete(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """DELETE soft-deletes; subsequent GET returns 404."""
        # Create
        create_resp = client.post(
            "/api/v1/base-classes",
            headers=_auth_headers(auth_token),
            json={"slug": "to-delete", "name": "To Delete"},
        )
        assert create_resp.status_code == 201
        preset_id = create_resp.json()["id"]

        # Delete
        del_resp = client.delete(
            f"/api/v1/base-classes/{preset_id}",
            headers=_auth_headers(auth_token),
        )
        assert del_resp.status_code == 204

        # Get by ID → 404
        get_resp = client.get(
            f"/api/v1/base-classes/{preset_id}",
            headers=_auth_headers(auth_token),
        )
        assert get_resp.status_code == 404
        assert get_resp.json()["error_code"] == "base_class.not_found"


# =========================================================================
# Entity CRUD
# =========================================================================


class TestEntityCrud:
    """CRUD for /api/v1/entities."""

    def test_create_entity_with_valid_preset(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """POST /api/v1/entities with valid preset_slug returns 201."""
        response = client.post(
            "/api/v1/entities",
            headers=_auth_headers(auth_token),
            json={
                "name": "Alice Agent",
                "slug": "alice",
                "rank": "researcher",
                "preset_slug": "mi-shi",
                "display_name": "Alice",
                "display_color": "#FF5733",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["slug"] == "alice"
        assert body["name"] == "Alice Agent"
        assert body["preset_slug"] == "mi-shi"
        assert body["rank"] == "researcher"
        assert "id" in body

    def test_create_entity_with_invalid_preset(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """POST /api/v1/entities with nonexistent preset_slug returns 422."""
        response = client.post(
            "/api/v1/entities",
            headers=_auth_headers(auth_token),
            json={
                "name": "Bad Agent",
                "slug": "bad-agent",
                "preset_slug": "nonexistent",
            },
        )
        assert response.status_code == 422
        body = response.json()
        assert body["error_code"] == "entity.preset_not_found"

    def test_create_entity_duplicate_slug(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """Creating an entity with an existing slug returns 409."""
        payload = {
            "name": "First",
            "slug": "dup-emp",
        }
        resp1 = client.post(
            "/api/v1/entities",
            headers=_auth_headers(auth_token),
            json=payload,
        )
        assert resp1.status_code == 201

        resp2 = client.post(
            "/api/v1/entities",
            headers=_auth_headers(auth_token),
            json=payload,
        )
        assert resp2.status_code == 409
        assert resp2.json()["error_code"] == "entity.slug_taken"

    def test_delete_entity_soft_delete(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """DELETE soft-deletes; subsequent GET returns 404."""
        create_resp = client.post(
            "/api/v1/entities",
            headers=_auth_headers(auth_token),
            json={"name": "To Delete", "slug": "to-delete-emp"},
        )
        assert create_resp.status_code == 201
        emp_id = create_resp.json()["id"]

        del_resp = client.delete(
            f"/api/v1/entities/{emp_id}",
            headers=_auth_headers(auth_token),
        )
        assert del_resp.status_code == 204

        get_resp = client.get(
            f"/api/v1/entities/{emp_id}",
            headers=_auth_headers(auth_token),
        )
        assert get_resp.status_code == 404
        assert get_resp.json()["error_code"] == "entity.not_found"


# =========================================================================
# Workspace CRUD
# =========================================================================


class TestWorkspaceCrud:
    """CRUD for /api/v1/workspaces."""

    def test_create_workspace(self, client: TestClient, auth_token: str) -> None:
        """POST /api/v1/workspaces returns 201 with the new workspace."""
        response = client.post(
            "/api/v1/workspaces",
            headers=_auth_headers(auth_token),
            json={
                "name": "War Room",
                "slug": "war-room",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["slug"] == "war-room"
        assert body["name"] == "War Room"
        assert "id" in body

    def test_create_workspace_duplicate_slug(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """Creating an workspace with an existing slug returns 409."""
        payload = {"name": "Original", "slug": "dup-workspace"}
        resp1 = client.post(
            "/api/v1/workspaces",
            headers=_auth_headers(auth_token),
            json=payload,
        )
        assert resp1.status_code == 201

        resp2 = client.post(
            "/api/v1/workspaces",
            headers=_auth_headers(auth_token),
            json=payload,
        )
        assert resp2.status_code == 409
        assert resp2.json()["error_code"] == "workspace.slug_taken"

    def test_delete_workspace_soft_delete(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """DELETE soft-deletes; subsequent GET returns 404."""
        create_resp = client.post(
            "/api/v1/workspaces",
            headers=_auth_headers(auth_token),
            json={"name": "To Delete", "slug": "to-delete-workspace"},
        )
        assert create_resp.status_code == 201
        workspace_id = create_resp.json()["id"]

        del_resp = client.delete(
            f"/api/v1/workspaces/{workspace_id}",
            headers=_auth_headers(auth_token),
        )
        assert del_resp.status_code == 204

        get_resp = client.get(
            f"/api/v1/workspaces/{workspace_id}",
            headers=_auth_headers(auth_token),
        )
        assert get_resp.status_code == 404
        assert get_resp.json()["error_code"] == "workspace.not_found"

    def test_list_workspaces(self, client: TestClient, auth_token: str) -> None:
        """GET /api/v1/workspaces returns a paginated list."""
        # Create two workspaces
        client.post(
            "/api/v1/workspaces",
            headers=_auth_headers(auth_token),
            json={"name": "Workspace A", "slug": "workspace-a"},
        )
        client.post(
            "/api/v1/workspaces",
            headers=_auth_headers(auth_token),
            json={"name": "Workspace B", "slug": "workspace-b"},
        )

        response = client.get(
            "/api/v1/workspaces",
            headers=_auth_headers(auth_token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 2
        assert len(body["items"]) >= 2
        slugs = {item["slug"] for item in body["items"]}
        assert "workspace-a" in slugs
        assert "workspace-b" in slugs
