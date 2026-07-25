"""Integration tests for P6 Blackboard system — blackboard, files, vault, memory, permissions.

All tests use the ``client`` fixture (isolated DB clone + JWT auth).
Each test creates its own office/membership/employee data.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models.user import User


@pytest.fixture(autouse=True)
def _raise_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.middleware.rate_limit.MAX_REQUESTS_PER_WINDOW",
        100_000,
    )


@pytest.fixture
def auth_token(client: TestClient) -> str:
    client.post("/api/v1/auth/register", json={
        "username": "blackboard_test",
        "email": "bb_test@test.com",
        "password": "password123",
    })
    resp = client.post("/api/v1/auth/login", json={
        "username": "blackboard_test",
        "password": "password123",
    })
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def auth_user_id(auth_token: str, session: AsyncSession) -> str:
    result = await session.execute(
        select(User).where(User.username == "blackboard_test"),
    )
    user: User = result.scalars().first()
    return user.id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup_office_and_membership(
    client: TestClient,
    token: str,
    user_id: str,
    office_name: str = "Test Office",
    office_slug: str = "test-office",
    role: str = "owner",
) -> str:
    h = _auth(token)
    resp = client.post("/api/v1/offices", headers=h, json={
        "name": office_name,
        "slug": office_slug,
    })
    assert resp.status_code == 201
    office_id = resp.json()["id"]

    resp = client.post("/api/v1/messaging/memberships", headers=h, json={
        "office_id": office_id,
        "user_id": user_id,
        "role": role,
    })
    assert resp.status_code == 201
    return office_id


def _register_and_login(client: TestClient, username: str) -> str:
    email = f"{username}@test.com"
    client.post("/api/v1/auth/register", json={
        "username": username,
        "email": email,
        "password": "password123",
    })
    resp = client.post("/api/v1/auth/login", json={
        "username": username,
        "password": "password123",
    })
    return resp.json()["access_token"]


def _create_employee(client: TestClient, token: str, slug: str, name: str) -> str:
    resp = client.post("/api/v1/employees", headers=_auth(token), json={
        "name": name,
        "slug": slug,
    })
    assert resp.status_code == 201
    return resp.json()["id"]


# =========================================================================
# Blackboard
# =========================================================================


class TestBlackboard:
    def test_lazy_create_blackboard(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="BB Lazy Office", office_slug="bb-lazy",
        )

        resp1 = client.get(f"/api/v1/blackboard/{office_id}", headers=h)
        assert resp1.status_code == 200
        body1 = resp1.json()
        assert "id" in body1
        assert body1["office_id"] == office_id
        assert body1["content"] is None
        assert body1["manual_notes"] is None

        resp2 = client.get(f"/api/v1/blackboard/{office_id}", headers=h)
        assert resp2.status_code == 200
        assert resp2.json()["id"] == body1["id"]

    def test_update_blackboard_content(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="BB Update Office", office_slug="bb-update",
        )

        client.get(f"/api/v1/blackboard/{office_id}", headers=h)

        resp = client.patch(f"/api/v1/blackboard/{office_id}", headers=h, json={
            "content": "hello",
            "manual_notes": "notes",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["content"] == "hello"
        assert body["manual_notes"] == "notes"

        resp2 = client.get(f"/api/v1/blackboard/{office_id}", headers=h)
        assert resp2.status_code == 200
        assert resp2.json()["content"] == "hello"


# =========================================================================
# BlackboardFile
# =========================================================================


class TestBlackboardFile:
    def test_create_directory_and_file(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="Dir Test Office", office_slug="dir-test",
        )

        resp = client.post(
            f"/api/v1/blackboard/{office_id}/files",
            headers=h,
            json={"office_id": office_id, "name": "docs", "is_directory": True},
        )
        assert resp.status_code == 201
        assert resp.json()["is_directory"] is True

        resp = client.post(
            f"/api/v1/blackboard/{office_id}/files",
            headers=h,
            json={
                "office_id": office_id,
                "name": "readme.txt",
                "parent_path": "/docs",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["parent_path"] == "/docs"

        resp = client.get(
            f"/api/v1/blackboard/{office_id}/files?parent_path=/docs",
            headers=h,
        )
        assert resp.status_code == 200
        names = [item["name"] for item in resp.json()["items"]]
        assert "readme.txt" in names

    def test_duplicate_path_rejected(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="Dup Test Office", office_slug="dup-test",
        )

        payload = {"office_id": office_id, "name": "data.json"}

        resp1 = client.post(
            f"/api/v1/blackboard/{office_id}/files",
            headers=h,
            json=payload,
        )
        assert resp1.status_code == 201

        resp2 = client.post(
            f"/api/v1/blackboard/{office_id}/files",
            headers=h,
            json=payload,
        )
        assert resp2.status_code == 409
        assert resp2.json()["error_code"] == "blackboard.duplicate_path"

    def test_delete_nonempty_directory_refused(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="Del Dir Office", office_slug="del-dir",
        )

        resp = client.post(
            f"/api/v1/blackboard/{office_id}/files",
            headers=h,
            json={"office_id": office_id, "name": "tmp", "is_directory": True},
        )
        assert resp.status_code == 201
        dir_id = resp.json()["id"]

        resp = client.post(
            f"/api/v1/blackboard/{office_id}/files",
            headers=h,
            json={
                "office_id": office_id,
                "name": "temp.log",
                "parent_path": "/tmp",
            },
        )
        assert resp.status_code == 201
        file_id = resp.json()["id"]

        resp = client.delete(
            f"/api/v1/blackboard/{office_id}/files/{dir_id}",
            headers=h,
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "blackboard.directory_not_empty"

        resp = client.delete(
            f"/api/v1/blackboard/{office_id}/files/{file_id}",
            headers=h,
        )
        assert resp.status_code == 204

        resp = client.delete(
            f"/api/v1/blackboard/{office_id}/files/{dir_id}",
            headers=h,
        )
        assert resp.status_code == 204


# =========================================================================
# Vault
# =========================================================================


class TestVault:
    def test_archive_file_to_vault(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="Vault Office", office_slug="vault-office",
        )

        resp = client.post(
            f"/api/v1/blackboard/{office_id}/files",
            headers=h,
            json={"office_id": office_id, "name": "archive_me.txt"},
        )
        assert resp.status_code == 201
        file_id = resp.json()["id"]

        resp = client.post(
            f"/api/v1/blackboard/{office_id}/files/{file_id}/archive",
            headers=h,
        )
        assert resp.status_code == 201
        entry = resp.json()
        assert "id" in entry
        assert entry["source_type"] == "blackboard_file"
        assert entry["source_ref"] == file_id

        resp = client.get(
            f"/api/v1/blackboard/{office_id}/files/{file_id}",
            headers=h,
        )
        assert resp.status_code == 404

        resp = client.get(
            f"/api/v1/blackboard/{office_id}/vault/entries",
            headers=h,
        )
        assert resp.status_code == 200
        entries = resp.json()["items"]
        assert any(e["source_type"] == "blackboard_file" for e in entries)


# =========================================================================
# Memory
# =========================================================================


class TestMemory:
    def test_append_and_list_memory(
        self,
        client: TestClient,
        auth_token: str,
    ) -> None:
        h = _auth(auth_token)
        employee_id = _create_employee(
            client, auth_token, "memory-emp", "Memory Employee",
        )

        resp = client.post("/api/v1/memory/entries", headers=h, json={
            "employee_id": employee_id,
            "kind": "experience",
            "content": "test memory content",
        })
        assert resp.status_code == 201
        entry = resp.json()
        assert entry["kind"] == "experience"
        assert entry["content"] == "test memory content"

        resp = client.get(
            f"/api/v1/memory/entries?employee_id={employee_id}",
            headers=h,
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(e["id"] == entry["id"] for e in items)

    def test_memory_keyed_lookup(
        self,
        client: TestClient,
        auth_token: str,
    ) -> None:
        h = _auth(auth_token)
        employee_id = _create_employee(
            client, auth_token, "keyed-emp", "Keyed Employee",
        )

        resp1 = client.post("/api/v1/memory/entries", headers=h, json={
            "employee_id": employee_id,
            "kind": "lesson",
            "key": "lesson-1",
            "content": "first version",
        })
        assert resp1.status_code == 201

        resp2 = client.post("/api/v1/memory/entries", headers=h, json={
            "employee_id": employee_id,
            "kind": "lesson",
            "key": "lesson-1",
            "content": "second version",
        })
        assert resp2.status_code == 201
        second_id = resp2.json()["id"]

        resp = client.get(
            f"/api/v1/memory/entries?employee_id={employee_id}&key=lesson-1",
            headers=h,
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["id"] == second_id
        assert items[0]["content"] == "second version"


# =========================================================================
# Permissions
# =========================================================================


class TestPermissions:
    @pytest.mark.asyncio
    async def test_viewer_cannot_write(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="Perm Viewer Office", office_slug="perm-viewer",
        )

        _register_and_login(client, "viewer_user")

        result = await session.execute(
            select(User).where(User.username == "viewer_user"),
        )
        viewer = result.scalars().first()
        assert viewer is not None

        resp = client.post("/api/v1/messaging/memberships", headers=h, json={
            "office_id": office_id,
            "user_id": viewer.id,
            "role": "viewer",
        })
        assert resp.status_code == 201

        viewer_token = client.post("/api/v1/auth/login", json={
            "username": "viewer_user",
            "password": "password123",
        }).json()["access_token"]
        viewer_h = _auth(viewer_token)

        resp = client.post(
            f"/api/v1/blackboard/{office_id}/files",
            headers=viewer_h,
            json={"office_id": office_id, "name": "should_fail.txt"},
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "office.insufficient_role"

    def test_nonmember_access_denied(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="NoMem Office", office_slug="nomem-office",
        )

        nonmember_token = _register_and_login(client, "nonmember_user")
        nonmember_h = _auth(nonmember_token)

        resp = client.get(
            f"/api/v1/blackboard/{office_id}",
            headers=nonmember_h,
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "office.not_member"
