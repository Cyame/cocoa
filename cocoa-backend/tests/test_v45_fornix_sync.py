"""v4.5 Fornix dual-write sync tests — H3 mount-mirror semantics.

DB ``FornixFile`` is the Portal/API truth source; the Host ``shared/`` tree is
a mirror written under a tmp ``FORNIX_ROOT`` (set in conftest
``pytest_configure``). These tests pin: CRUD dual-write to disk, the sync
failure path (5xx + a ``fornix.sync_failed`` event row), the archive → restore
roundtrip (content preserved), and vault ``archived_key`` search.
"""

import os

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.core.config import settings
from app.core.event_types import FORNIX_SYNC_FAILED
from app.models.event import Event
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
        "username": "fornix_v45_test",
        "email": "fornix_v45@test.com",
        "password": "password123",
    })
    resp = client.post("/api/v1/auth/login", json={
        "username": "fornix_v45_test",
        "password": "password123",
    })
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def auth_user_id(auth_token: str, session: AsyncSession) -> str:
    result = await session.execute(
        select(User).where(User.username == "fornix_v45_test"),
    )
    user: User = result.scalars().first()
    return user.id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup_workspace(client: TestClient, token: str, slug: str) -> str:
    resp = client.post("/api/v1/workspaces", headers=_auth(token), json={
        "name": f"Fornix {slug}",
        "slug": slug,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _mirror_path(workspace_id: str, parent_path: str | None, name: str) -> str:
    """Expected absolute mirror path under the tmp FORNIX_ROOT."""
    rel = name if not parent_path else f"{parent_path.strip('/')}/{name}"
    return os.path.join(settings.FORNIX_ROOT, workspace_id, "shared", rel)


# =========================================================================
# CRUD dual-write
# =========================================================================


class TestDualWrite:
    def test_create_file_writes_to_disk(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token, "fornix-dual")

        resp = client.post(
            f"/api/v1/central-hubs/{workspace_id}/files",
            headers=h,
            json={
                "workspace_id": workspace_id,
                "name": "readme.txt",
                "content": "hello mirror",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["content"] == "hello mirror"

        target = _mirror_path(workspace_id, None, "readme.txt")
        assert os.path.isfile(target)
        with open(target, encoding="utf-8") as fh:
            assert fh.read() == "hello mirror"

    def test_create_directory_and_nested_file_on_disk(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token, "fornix-dirs")

        resp = client.post(
            f"/api/v1/central-hubs/{workspace_id}/files",
            headers=h,
            json={"workspace_id": workspace_id, "name": "docs", "is_directory": True},
        )
        assert resp.status_code == 201, resp.text
        assert os.path.isdir(_mirror_path(workspace_id, None, "docs"))

        resp = client.post(
            f"/api/v1/central-hubs/{workspace_id}/files",
            headers=h,
            json={
                "workspace_id": workspace_id,
                "name": "notes.md",
                "parent_path": "/docs",
                "content": "nested",
            },
        )
        assert resp.status_code == 201, resp.text
        target = _mirror_path(workspace_id, "/docs", "notes.md")
        assert os.path.isfile(target)
        with open(target, encoding="utf-8") as fh:
            assert fh.read() == "nested"

    def test_rename_and_delete_sync_disk(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token, "fornix-move")

        resp = client.post(
            f"/api/v1/central-hubs/{workspace_id}/files",
            headers=h,
            json={"workspace_id": workspace_id, "name": "old.txt", "content": "x"},
        )
        assert resp.status_code == 201, resp.text
        file_id = resp.json()["id"]
        old_target = _mirror_path(workspace_id, None, "old.txt")
        assert os.path.isfile(old_target)

        resp = client.patch(
            f"/api/v1/central-hubs/{workspace_id}/files/{file_id}",
            headers=h,
            json={"name": "new.txt"},
        )
        assert resp.status_code == 200, resp.text
        new_target = _mirror_path(workspace_id, None, "new.txt")
        assert os.path.isfile(new_target)
        assert not os.path.exists(old_target)

        resp = client.delete(
            f"/api/v1/central-hubs/{workspace_id}/files/{file_id}",
            headers=h,
        )
        assert resp.status_code == 204, resp.text
        assert not os.path.exists(new_target)


# =========================================================================
# Sync failure path
# =========================================================================


class TestSyncFailure:
    async def test_create_sync_failure_returns_500_and_emits_event(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token, "fornix-fail")

        def _boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("app.services.fornix_sync.sync_write", _boom)

        resp = client.post(
            f"/api/v1/central-hubs/{workspace_id}/files",
            headers=h,
            json={"workspace_id": workspace_id, "name": "fail.txt", "content": "x"},
        )
        assert resp.status_code == 500, resp.text
        assert resp.json()["error_code"] == "central_hub.fornix.sync_failed"
        assert resp.json()["details"]["workspace_id"] == workspace_id

        # No DB row was left behind (rolled back).
        resp = client.get(
            f"/api/v1/central-hubs/{workspace_id}/files",
            headers=h,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

        # The failure event was persisted (never a silent DB-only write).
        result = await session.execute(
            select(Event).where(Event.type == FORNIX_SYNC_FAILED)
        )
        events = result.scalars().all()
        assert len(events) == 1
        assert events[0].payload["workspace_id"] == workspace_id


# =========================================================================
# Archive → restore
# =========================================================================


class TestVaultRestore:
    def test_archive_restore_roundtrip_preserves_content(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token, "fornix-vault")

        resp = client.post(
            f"/api/v1/central-hubs/{workspace_id}/files",
            headers=h,
            json={"workspace_id": workspace_id, "name": "keep.txt", "content": "hello vault"},
        )
        assert resp.status_code == 201, resp.text
        file_id = resp.json()["id"]
        target = _mirror_path(workspace_id, None, "keep.txt")
        assert os.path.isfile(target)

        resp = client.post(
            f"/api/v1/central-hubs/{workspace_id}/files/{file_id}/archive",
            headers=h,
        )
        assert resp.status_code == 201, resp.text
        entry_id = resp.json()["id"]
        assert not os.path.exists(target)

        resp = client.post(
            f"/api/v1/central-hubs/{workspace_id}/vault/entries/{entry_id}/restore",
            headers=h,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == file_id
        assert body["content"] == "hello vault"

        assert os.path.isfile(target)
        with open(target, encoding="utf-8") as fh:
            assert fh.read() == "hello vault"

        # The vault entry is soft-deleted; the file is active again.
        resp = client.get(
            f"/api/v1/central-hubs/{workspace_id}/vault/entries",
            headers=h,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

        resp = client.get(
            f"/api/v1/central-hubs/{workspace_id}/files/{file_id}",
            headers=h,
        )
        assert resp.status_code == 200

    def test_restore_conflict_returns_409(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token, "fornix-conflict")

        resp = client.post(
            f"/api/v1/central-hubs/{workspace_id}/files",
            headers=h,
            json={"workspace_id": workspace_id, "name": "x.txt", "content": "first"},
        )
        assert resp.status_code == 201, resp.text
        file_id = resp.json()["id"]

        resp = client.post(
            f"/api/v1/central-hubs/{workspace_id}/files/{file_id}/archive",
            headers=h,
        )
        assert resp.status_code == 201, resp.text
        entry_id = resp.json()["id"]

        resp = client.post(
            f"/api/v1/central-hubs/{workspace_id}/files",
            headers=h,
            json={"workspace_id": workspace_id, "name": "x.txt", "content": "second"},
        )
        assert resp.status_code == 201, resp.text

        resp = client.post(
            f"/api/v1/central-hubs/{workspace_id}/vault/entries/{entry_id}/restore",
            headers=h,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["error_code"] == "central_hub.fornix.duplicate_path"


# =========================================================================
# Vault archived_key search
# =========================================================================


class TestVaultArchivedKeySearch:
    def test_partial_case_insensitive_key_filter(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        h = _auth(auth_token)
        workspace_id = _setup_workspace(client, auth_token, "fornix-search")

        for name, key in [("a.txt", "docs-v1-key"), ("b.txt", "notes-key")]:
            resp = client.post(
                f"/api/v1/central-hubs/{workspace_id}/files",
                headers=h,
                json={"workspace_id": workspace_id, "name": name, "storage_key": key},
            )
            assert resp.status_code == 201, resp.text
            file_id = resp.json()["id"]
            resp = client.post(
                f"/api/v1/central-hubs/{workspace_id}/files/{file_id}/archive",
                headers=h,
            )
            assert resp.status_code == 201, resp.text

        resp = client.get(
            f"/api/v1/central-hubs/{workspace_id}/vault/entries?archived_key=DOCS",
            headers=h,
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["archived_key"] == "docs-v1-key"
