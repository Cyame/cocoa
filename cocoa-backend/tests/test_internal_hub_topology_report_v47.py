"""v4.7 H6: internal hub_read / hub_write / topology / report endpoints.

Covers:

- ``POST /internal/hub/read`` — mount-contract read of existing files;
  ``..`` traversal rejected with 400; missing file 404.
- ``POST /internal/hub/write`` — shared scope dual-writes the FornixFile
  row (uploader = instance, XOR) + the ``<FORNIX_ROOT>/<workspace_id>/shared/``
  mirror file; duplicate path 409; work scope validates the pod-local
  ``work/`` path and records an audit event without mirroring.
- ``GET /internal/topology`` — caller instance + Passage neighbors with
  loop-status / glow snapshots.
- ``POST /internal/report`` — V47-10 tldr hard validation (400 without tldr
  for > 240 chars of prose) and ``harness.report_received`` event emission.

Mounts the internal router on a bare FastAPI app (phase11c convention) with
the production error handlers so CocoaError (e.g. V47-10) serializes to the
standard envelope instead of a bare 500.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

import app.core.db as db_mod
from app.api.deps import get_db
from app.api.v1.internal import router as internal_router
from app.core.db import get_session_factory
from app.core.errors import CocoaError
from app.core.event_types import (
    FORNIX_FILE_WRITTEN,
    HARNESS_REPORT_RECEIVED,
)
from app.main import cocoa_error_handler, validation_exception_handler
from app.models.central_hub import CentralHub, FornixFile
from app.models.event import Event
from app.models.loop_state import LoopStatus
from app.models.workspace import Membership, Passage
from app.services import fornix_sync

_TEST_TOKEN = "test-cocoa-internal-token"

_AUTH_HEADERS = {"Authorization": f"Bearer {_TEST_TOKEN}"}


@pytest.fixture
def internal_client(db_url: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Minimal TestClient mounting only the internal router.

    Same pattern as test_phase11c_internal_endpoints.py, plus the production
    CocoaError / validation handlers so domain errors (V47-10 tldr rules,
    path traversal) come back in the standard error envelope.
    """
    monkeypatch.setattr("app.core.config.settings.DATABASE_URL", db_url)
    db_mod._engine = None
    db_mod._session_factory = None
    factory = get_session_factory()

    async def _override_get_db():  # type: ignore[no-untyped-def]
        async with factory() as s:
            yield s

    app = FastAPI()
    app.add_exception_handler(CocoaError, cocoa_error_handler)
    app.add_exception_handler(
        RequestValidationError, validation_exception_handler
    )
    app.include_router(internal_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


@pytest.fixture(autouse=True)
def _env_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COCOA_API_TOKEN", _TEST_TOKEN)


async def _seed_fornix_file(
    session: AsyncSession,
    workspace_id: str,
    instance_id: str,
    *,
    name: str,
    parent_path: str | None,
    content: str = "",
    is_directory: bool = False,
) -> FornixFile:
    """Create a FornixFile row + its disk mirror (like central_hubs create)."""
    hub = (
        await session.execute(
            select(CentralHub).where(
                CentralHub.workspace_id == workspace_id,
                CentralHub.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if hub is None:
        hub = CentralHub(workspace_id=workspace_id)
        session.add(hub)
        await session.flush()

    file = FornixFile(
        workspace_id=workspace_id,
        central_hub_id=hub.id,
        name=name,
        parent_path=parent_path,
        storage_key=str(uuid.uuid4()),
        content=content,
        is_directory=is_directory,
        uploader_instance_id=instance_id,
    )
    session.add(file)
    await session.flush()
    fornix_sync.sync_write(
        workspace_id,
        parent_path,
        name,
        content=content,
        is_directory=is_directory,
    )
    return file


# ---------------------------------------------------------------------------
# POST /internal/hub/read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hub_read_returns_existing_file_content(
    internal_client: TestClient,
    session: AsyncSession,
    workspace_factory,
    instance_factory,
) -> None:
    workspace = await workspace_factory()
    instance = await instance_factory(workspace_id=workspace.id)
    await _seed_fornix_file(
        session, workspace.id, instance.id, name="docs", parent_path=None,
        is_directory=True,
    )
    await _seed_fornix_file(
        session, workspace.id, instance.id, name="plan.md",
        parent_path="/docs", content="hello hub",
    )
    await session.commit()

    resp = internal_client.post(
        "/api/v1/internal/hub/read",
        json={
            "workspace_id": workspace.id,
            "refs": [{"scope": "hub", "path": "docs/plan.md"}],
        },
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["files"]) == 1
    file = body["files"][0]
    assert file["scope"] == "hub"
    assert file["path"] == "docs/plan.md"
    assert file["content"] == "hello hub"
    assert file["size"] == 9


@pytest.mark.asyncio
async def test_hub_read_rejects_traversal(
    internal_client: TestClient, session: AsyncSession, workspace_factory
) -> None:
    workspace = await workspace_factory()
    await session.commit()

    resp = internal_client.post(
        "/api/v1/internal/hub/read",
        json={
            "workspace_id": workspace.id,
            "refs": [{"scope": "hub", "path": "../secrets.md"}],
        },
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error_code"] == "internal.hub.path_invalid"


@pytest.mark.asyncio
async def test_hub_read_missing_file_404(
    internal_client: TestClient, session: AsyncSession, workspace_factory
) -> None:
    workspace = await workspace_factory()
    await session.commit()

    resp = internal_client.post(
        "/api/v1/internal/hub/read",
        json={
            "workspace_id": workspace.id,
            "refs": [{"scope": "hub", "path": "nope.md"}],
        },
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error_code"] == "internal.hub.file_not_found"


# ---------------------------------------------------------------------------
# POST /internal/hub/write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hub_write_shared_dual_writes_disk_and_row(
    internal_client: TestClient,
    session: AsyncSession,
    workspace_factory,
    instance_factory,
) -> None:
    workspace = await workspace_factory()
    instance = await instance_factory(workspace_id=workspace.id)
    await _seed_fornix_file(
        session, workspace.id, instance.id, name="docs", parent_path=None,
        is_directory=True,
    )
    await session.commit()

    resp = internal_client.post(
        "/api/v1/internal/hub/write",
        json={
            "workspace_id": workspace.id,
            "instance_id": instance.id,
            "scope": "shared",
            "path": "docs/plan.md",
            "content": "promoted plan",
        },
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["file_id"]
    assert body["mirrored"] is True

    row = (
        await session.execute(
            select(FornixFile).where(FornixFile.id == body["file_id"])
        )
    ).scalar_one()
    assert row.name == "plan.md"
    assert row.parent_path == "/docs"
    assert row.uploader_instance_id == instance.id
    assert row.uploader_user_id is None  # XOR: instance uploader only
    assert row.content == "promoted plan"

    # Manual-QA: the shared/ mirror file really exists on disk.
    disk_path = os.path.join(
        fornix_sync.mirror_root(workspace.id), "docs", "plan.md"
    )
    assert os.path.exists(disk_path), disk_path
    with open(disk_path, "r", encoding="utf-8") as fh:
        assert fh.read() == "promoted plan"


@pytest.mark.asyncio
async def test_hub_write_shared_duplicate_409(
    internal_client: TestClient,
    session: AsyncSession,
    workspace_factory,
    instance_factory,
) -> None:
    workspace = await workspace_factory()
    instance = await instance_factory(workspace_id=workspace.id)
    # Pre-existing row (seeded via the test session to avoid a second portal
    # request reusing a cross-loop pooled connection).
    await _seed_fornix_file(
        session, workspace.id, instance.id, name="plan.md",
        parent_path=None, content="first",
    )
    await session.commit()

    resp = internal_client.post(
        "/api/v1/internal/hub/write",
        json={
            "workspace_id": workspace.id,
            "instance_id": instance.id,
            "scope": "shared",
            "path": "plan.md",
            "content": "second",
        },
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error_code"] == "central_hub.fornix.duplicate_path"


@pytest.mark.asyncio
async def test_hub_write_work_validates_path_and_audits_only(
    internal_client: TestClient,
    session: AsyncSession,
    workspace_factory,
    instance_factory,
) -> None:
    workspace = await workspace_factory()
    instance = await instance_factory(workspace_id=workspace.id)
    await session.commit()

    resp = internal_client.post(
        "/api/v1/internal/hub/write",
        json={
            "workspace_id": workspace.id,
            "instance_id": instance.id,
            "scope": "work",
            "path": "work/scratch.md",
            "content": "tmp",
        },
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["scope"] == "work"
    assert body["mirrored"] is False
    assert body["event_id"]

    rows = (
        await session.execute(
            select(FornixFile).where(
                FornixFile.workspace_id == workspace.id,
                FornixFile.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    assert rows == []  # work files are never mirrored to the DB

    event = (
        await session.execute(
            select(Event).where(Event.id == body["event_id"])
        )
    ).scalar_one()
    assert event.type == FORNIX_FILE_WRITTEN
    assert event.payload["path"] == "work/scratch.md"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_path", ["../escape.md", "shared/x.md", "work", "work/"]
)
async def test_hub_write_work_rejects_illegal_paths(
    internal_client: TestClient,
    session: AsyncSession,
    workspace_factory,
    instance_factory,
    bad_path: str,
) -> None:
    workspace = await workspace_factory()
    instance = await instance_factory(workspace_id=workspace.id)
    await session.commit()

    resp = internal_client.post(
        "/api/v1/internal/hub/write",
        json={
            "workspace_id": workspace.id,
            "instance_id": instance.id,
            "scope": "work",
            "path": bad_path,
            "content": "x",
        },
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# GET /internal/topology
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_topology_returns_self_and_passage_neighbors(
    internal_client: TestClient,
    session: AsyncSession,
    workspace_factory,
    entity_factory,
    instance_factory,
    loop_state_factory,
) -> None:
    workspace = await workspace_factory()
    ent_a = await entity_factory(slug="ent-topo-a")
    ent_b = await entity_factory(slug="ent-topo-b")
    inst_a = await instance_factory(workspace_id=workspace.id, entity_id=ent_a.id)
    inst_b = await instance_factory(workspace_id=workspace.id, entity_id=ent_b.id)

    mem_a = Membership(
        workspace_id=workspace.id, instance_id=inst_a.id, posx=0, posy=0
    )
    mem_b = Membership(
        workspace_id=workspace.id, instance_id=inst_b.id, posx=1, posy=1
    )
    session.add_all([mem_a, mem_b])
    await session.flush()
    lo, hi = sorted([mem_a.id, mem_b.id])
    session.add(
        Passage(
            workspace_id=workspace.id,
            from_membership_id=lo,
            to_membership_id=hi,
            is_active=True,
            mode="dual",
        )
    )
    await loop_state_factory(inst_a, loop_status=LoopStatus.running.value)
    await loop_state_factory(inst_b, loop_status=LoopStatus.idle.value)
    await session.commit()

    resp = internal_client.get(
        "/api/v1/internal/topology",
        params={"instance_id": inst_a.id},
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["self"]["membership_id"] == mem_a.id
    assert body["self"]["entity_slug"] == ent_a.slug
    assert body["self"]["loop_status"] == "running"
    assert body["self"]["glow"] == {
        "color": "#10b981",
        "intensity": "strong",
    }

    assert len(body["neighbors"]) == 1
    neighbor = body["neighbors"][0]
    assert neighbor["membership_id"] == mem_b.id
    assert neighbor["entity_slug"] == ent_b.slug
    assert neighbor["loop_status"] == "idle"
    assert neighbor["glow"] == {"color": "#eab308", "intensity": "medium"}


@pytest.mark.asyncio
async def test_topology_unknown_instance_404(
    internal_client: TestClient, session: AsyncSession
) -> None:
    resp = internal_client.get(
        "/api/v1/internal/topology",
        params={"instance_id": "no-such-instance"},
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error_code"] == "internal.topology.instance_not_found"


# ---------------------------------------------------------------------------
# POST /internal/report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_report_long_prose_without_tldr_rejected(
    internal_client: TestClient,
    session: AsyncSession,
    workspace_factory,
    instance_factory,
) -> None:
    """V47-10: > 240 chars of changes/validation/blockers requires tldr."""
    workspace = await workspace_factory()
    instance = await instance_factory(workspace_id=workspace.id)
    await session.commit()

    resp = internal_client.post(
        "/api/v1/internal/report",
        json={
            "workspace_id": workspace.id,
            "instance_id": instance.id,
            "outcome": "ok",
            "changes": ["x" * 241],
        },
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["message_key"] == "errors.internal.tldr_required"


@pytest.mark.asyncio
async def test_report_success_emits_harness_report_event(
    internal_client: TestClient,
    session: AsyncSession,
    workspace_factory,
    instance_factory,
) -> None:
    workspace = await workspace_factory()
    instance = await instance_factory(workspace_id=workspace.id)
    await session.commit()

    resp = internal_client.post(
        "/api/v1/internal/report",
        json={
            "workspace_id": workspace.id,
            "instance_id": instance.id,
            "outcome": "ok",
            "tldr": "plan promoted",
            "changes": ["wrote docs/plan.md"],
            "validation": ["lint clean"],
            "blockers": [],
            "content_refs": [
                {"scope": "hub", "path": "docs/plan.md", "label": "plan"}
            ],
        },
        headers=_AUTH_HEADERS,
    )
    assert resp.status_code == 202, resp.text
    event_id = resp.json()["event_id"]
    assert event_id

    event = (
        await session.execute(
            select(Event).where(Event.id == event_id)
        )
    ).scalar_one()
    assert event.type == HARNESS_REPORT_RECEIVED
    assert event.actor_type == "instance"
    assert event.actor_id == instance.id
    payload = event.payload
    assert payload["tldr"] == "plan promoted"
    assert payload["outcome"] == "ok"
    assert payload["changes"] == ["wrote docs/plan.md"]
    assert payload["validation"] == ["lint clean"]
    assert payload["blockers"] == []
    assert payload["content_refs"][0]["path"] == "docs/plan.md"


# ---------------------------------------------------------------------------
# Token gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_endpoints_require_internal_token(
    internal_client: TestClient, session: AsyncSession, workspace_factory
) -> None:
    workspace = await workspace_factory()
    await session.commit()

    resp = internal_client.post(
        "/api/v1/internal/hub/read",
        json={
            "workspace_id": workspace.id,
            "refs": [{"scope": "hub", "path": "a.md"}],
        },
    )
    assert resp.status_code == 401

    resp = internal_client.get(
        "/api/v1/internal/topology", params={"instance_id": "nope"}
    )
    assert resp.status_code == 401
