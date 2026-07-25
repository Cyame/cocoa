"""Integration tests for P4 CRUD endpoints — employee-presets, employees, offices.

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
# EmployeePreset CRUD
# =========================================================================


class TestEmployeePresetCrud:
    """CRUD for /api/v1/employee-presets."""

    def test_list_employee_presets(self, client: TestClient, auth_token: str) -> None:
        """GET /api/v1/employee-presets returns the 6 built-in presets."""
        response = client.get(
            "/api/v1/employee-presets",
            headers=_auth_headers(auth_token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 6
        slugs = {item["slug"] for item in body["items"]}
        for expected in ("mi-shi", "zhu-jin", "ling-shi", "you-hun", "heng-pan", "zong-jian"):
            assert expected in slugs, f"Built-in preset {expected} missing"

    def test_create_employee_preset(self, client: TestClient, auth_token: str) -> None:
        """POST /api/v1/employee-presets returns 201 with the new preset."""
        response = client.post(
            "/api/v1/employee-presets",
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

    def test_create_employee_preset_duplicate_slug(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """Creating a preset with an existing slug returns 409."""
        payload = {
            "slug": "dup-slug",
            "name": "Original",
        }
        resp1 = client.post(
            "/api/v1/employee-presets",
            headers=_auth_headers(auth_token),
            json=payload,
        )
        assert resp1.status_code == 201

        resp2 = client.post(
            "/api/v1/employee-presets",
            headers=_auth_headers(auth_token),
            json=payload,
        )
        assert resp2.status_code == 409
        assert resp2.json()["error_code"] == "employee_preset.slug_taken"

    def test_delete_employee_preset_soft_delete(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """DELETE soft-deletes; subsequent GET returns 404."""
        # Create
        create_resp = client.post(
            "/api/v1/employee-presets",
            headers=_auth_headers(auth_token),
            json={"slug": "to-delete", "name": "To Delete"},
        )
        assert create_resp.status_code == 201
        preset_id = create_resp.json()["id"]

        # Delete
        del_resp = client.delete(
            f"/api/v1/employee-presets/{preset_id}",
            headers=_auth_headers(auth_token),
        )
        assert del_resp.status_code == 204

        # Get by ID → 404
        get_resp = client.get(
            f"/api/v1/employee-presets/{preset_id}",
            headers=_auth_headers(auth_token),
        )
        assert get_resp.status_code == 404
        assert get_resp.json()["error_code"] == "employee_preset.not_found"


# =========================================================================
# Employee CRUD
# =========================================================================


class TestEmployeeCrud:
    """CRUD for /api/v1/employees."""

    def test_create_employee_with_valid_preset(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """POST /api/v1/employees with valid preset_slug returns 201."""
        response = client.post(
            "/api/v1/employees",
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

    def test_create_employee_with_invalid_preset(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """POST /api/v1/employees with nonexistent preset_slug returns 422."""
        response = client.post(
            "/api/v1/employees",
            headers=_auth_headers(auth_token),
            json={
                "name": "Bad Agent",
                "slug": "bad-agent",
                "preset_slug": "nonexistent",
            },
        )
        assert response.status_code == 422
        body = response.json()
        assert body["error_code"] == "employee.preset_not_found"

    def test_create_employee_duplicate_slug(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """Creating an employee with an existing slug returns 409."""
        payload = {
            "name": "First",
            "slug": "dup-emp",
        }
        resp1 = client.post(
            "/api/v1/employees",
            headers=_auth_headers(auth_token),
            json=payload,
        )
        assert resp1.status_code == 201

        resp2 = client.post(
            "/api/v1/employees",
            headers=_auth_headers(auth_token),
            json=payload,
        )
        assert resp2.status_code == 409
        assert resp2.json()["error_code"] == "employee.slug_taken"

    def test_delete_employee_soft_delete(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """DELETE soft-deletes; subsequent GET returns 404."""
        create_resp = client.post(
            "/api/v1/employees",
            headers=_auth_headers(auth_token),
            json={"name": "To Delete", "slug": "to-delete-emp"},
        )
        assert create_resp.status_code == 201
        emp_id = create_resp.json()["id"]

        del_resp = client.delete(
            f"/api/v1/employees/{emp_id}",
            headers=_auth_headers(auth_token),
        )
        assert del_resp.status_code == 204

        get_resp = client.get(
            f"/api/v1/employees/{emp_id}",
            headers=_auth_headers(auth_token),
        )
        assert get_resp.status_code == 404
        assert get_resp.json()["error_code"] == "employee.not_found"


# =========================================================================
# Office CRUD
# =========================================================================


class TestOfficeCrud:
    """CRUD for /api/v1/offices."""

    def test_create_office(self, client: TestClient, auth_token: str) -> None:
        """POST /api/v1/offices returns 201 with the new office."""
        response = client.post(
            "/api/v1/offices",
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

    def test_create_office_duplicate_slug(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """Creating an office with an existing slug returns 409."""
        payload = {"name": "Original", "slug": "dup-office"}
        resp1 = client.post(
            "/api/v1/offices",
            headers=_auth_headers(auth_token),
            json=payload,
        )
        assert resp1.status_code == 201

        resp2 = client.post(
            "/api/v1/offices",
            headers=_auth_headers(auth_token),
            json=payload,
        )
        assert resp2.status_code == 409
        assert resp2.json()["error_code"] == "office.slug_taken"

    def test_delete_office_soft_delete(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """DELETE soft-deletes; subsequent GET returns 404."""
        create_resp = client.post(
            "/api/v1/offices",
            headers=_auth_headers(auth_token),
            json={"name": "To Delete", "slug": "to-delete-office"},
        )
        assert create_resp.status_code == 201
        office_id = create_resp.json()["id"]

        del_resp = client.delete(
            f"/api/v1/offices/{office_id}",
            headers=_auth_headers(auth_token),
        )
        assert del_resp.status_code == 204

        get_resp = client.get(
            f"/api/v1/offices/{office_id}",
            headers=_auth_headers(auth_token),
        )
        assert get_resp.status_code == 404
        assert get_resp.json()["error_code"] == "office.not_found"

    def test_list_offices(self, client: TestClient, auth_token: str) -> None:
        """GET /api/v1/offices returns a paginated list."""
        # Create two offices
        client.post(
            "/api/v1/offices",
            headers=_auth_headers(auth_token),
            json={"name": "Office A", "slug": "office-a"},
        )
        client.post(
            "/api/v1/offices",
            headers=_auth_headers(auth_token),
            json={"name": "Office B", "slug": "office-b"},
        )

        response = client.get(
            "/api/v1/offices",
            headers=_auth_headers(auth_token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 2
        assert len(body["items"]) >= 2
        slugs = {item["slug"] for item in body["items"]}
        assert "office-a" in slugs
        assert "office-b" in slugs
