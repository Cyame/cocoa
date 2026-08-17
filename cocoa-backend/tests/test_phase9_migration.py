"""P9 Todo 1: Alembic migration round-trip + Membership coord unique index.

Covers:
1. Data preservation — insert membership with hex_q=5, hex_r=-3 BEFORE the
   rename migration runs; upgrade to head; verify posx=5, posy=-3;
   downgrade; verify hex_q=5, hex_r=-3 again. Run three passes so the
   migration is exercised as a round-trip.
2. Partial unique index — two active memberships in the same workspace at
   the same (posx, posy) must collide via IntegrityError (DB level) and
   the API must surface that as a 409 ConflictError
   ("membership.position_taken").

The round-trip is driven by shelling out to ``alembic upgrade`` /
``alembic downgrade`` against a dedicated database that is NOT the
shared ``cocoa_test_template``. asyncpg is used for raw row reads so
this test does not require the app's async engine.
"""

from __future__ import annotations

import os
import subprocess
import uuid

import asyncpg
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models.user import User
from app.models.workspace import Membership, Workspace

# ---------------------------------------------------------------------------
# 1. Alembic round-trip data-preservation test
# ---------------------------------------------------------------------------

_ADMIN_DSN = "postgresql://postgres:postgres@localhost:5432/postgres"
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PRE_REVISION = "bc3d9d6a84c8"  # revision immediately before our rename migration


def _run_alembic(db_url_asyncpg: str, *args: str) -> subprocess.CompletedProcess:
    """Run ``uv run alembic <args>`` with DATABASE_URL pinned."""
    env = {**os.environ, "DATABASE_URL": db_url_asyncpg}
    return subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=_BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )


async def _admin_exec(sql: str) -> None:
    conn = await asyncpg.connect(_ADMIN_DSN)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


@pytest.mark.asyncio
@pytest.mark.skip(
    reason="PRD-v2 nuclear rebuild dropped hex_q/hex_r rename; no historical data to round-trip",
)
async def test_round_trip_preserves_data_three_passes() -> None:
    """Insert membership before the rename migration; verify data survives
    3 passes of upgrade -> downgrade.

    Each pass:
        upgrade to head  -> SELECT posx, posy -> assert (5, -3)
        downgrade -1     -> SELECT hex_q, hex_r -> assert (5, -3)
    """
    db_name = f"cocoa_round_trip_{uuid.uuid4().hex[:8]}"
    db_url_asyncpg = (
        f"postgresql+asyncpg://postgres:postgres@localhost:5432/{db_name}"
    )
    pg_url_sync = f"postgresql://postgres:postgres@localhost:5432/{db_name}"

    try:
        await _admin_exec(f"CREATE DATABASE {db_name}")

        # Step 1: bring DB to pre-rename state
        result = _run_alembic(db_url_asyncpg, "upgrade", _PRE_REVISION)
        assert result.returncode == 0, (
            f"alembic upgrade {_PRE_REVISION} failed:\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

        conn = await asyncpg.connect(pg_url_sync)
        try:
            # Step 2: pre-insert workspaces + users + memberships at
            # hex_q=5, hex_r=-3
            user_id = str(uuid.uuid4())
            workspace_id = str(uuid.uuid4())
            membership_id = str(uuid.uuid4())

            await conn.execute(
                "INSERT INTO workspaces (id, name, slug, created_at, updated_at) "
                "VALUES ($1, $2, $3, now(), now())",
                workspace_id, "Round-Trip Workspace", f"rt-{uuid.uuid4().hex[:6]}",
            )
            await conn.execute(
                "INSERT INTO users (id, username, email, password_hash, "
                "is_super_admin, created_at, updated_at) "
                "VALUES ($1, $2, $3, $4, false, now(), now())",
                user_id, f"rt-user-{uuid.uuid4().hex[:6]}", "rt@test.com", "x",
            )
            await conn.execute(
                "INSERT INTO memberships ("
                "id, workspace_id, user_id, instance_id, hex_q, hex_r, role, "
                "created_at, updated_at"
                ") VALUES ("
                "$1, $2, $3, NULL, 5, -3, 'owner', now(), now()"
                ")",
                membership_id, workspace_id, user_id,
            )

            # Step 3: 3 passes of upgrade -> downgrade
            for pass_idx in range(1, 4):
                # upgrade to head
                result = _run_alembic(db_url_asyncpg, "upgrade", "head")
                assert result.returncode == 0, (
                    f"pass {pass_idx} upgrade head failed:\n"
                    f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
                )
                row = await conn.fetchrow(
                    "SELECT posx, posy FROM memberships WHERE id = $1",
                    membership_id,
                )
                assert row is not None, (
                    f"pass {pass_idx}: row vanished after upgrade"
                )
                assert (row["posx"], row["posy"]) == (5, -3), (
                    f"pass {pass_idx}: upgrade lost coord data: "
                    f"got ({row['posx']}, {row['posy']})"
                )

                # downgrade -1
                result = _run_alembic(db_url_asyncpg, "downgrade", _PRE_REVISION)
                assert result.returncode == 0, (
                    f"pass {pass_idx} downgrade -1 failed:\n"
                    f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
                )
                row = await conn.fetchrow(
                    "SELECT hex_q, hex_r FROM memberships WHERE id = $1",
                    membership_id,
                )
                assert row is not None, (
                    f"pass {pass_idx}: row vanished after downgrade"
                )
                assert (row["hex_q"], row["hex_r"]) == (5, -3), (
                    f"pass {pass_idx}: downgrade lost coord data: "
                    f"got ({row['hex_q']}, {row['hex_r']})"
                )
        finally:
            await conn.close()

        # Final state: bring DB to head so partial unique index exists.
        result = _run_alembic(db_url_asyncpg, "upgrade", "head")
        assert result.returncode == 0, (
            f"final upgrade head failed:\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

        conn = await asyncpg.connect(pg_url_sync)
        try:
            indexes = await conn.fetch(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE tablename = 'memberships' "
                "AND indexname = 'uq_memberships_workspace_pos'"
            )
            assert len(indexes) == 1, (
                f"uq_memberships_workspace_pos index missing after round-trip; "
                f"got {indexes}"
            )
        finally:
            await conn.close()
    finally:
        await _admin_exec(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")


# ---------------------------------------------------------------------------
# 2. Partial unique index ORM-level tests (uses conftest per-test clone)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unique_pos_constraint_blocks_duplicate_active(
    session: AsyncSession, namespace_factory,
) -> None:
    """Two active memberships in the same workspace at the same (posx, posy)
    must fail with IntegrityError because of the
    ``uq_memberships_workspace_pos`` partial unique index."""
    ns = await namespace_factory()
    workspace = Workspace(namespace_id=ns.id, name="Dup Pos Workspace", slug="dup-pos-workspace")
    session.add(workspace)
    await session.commit()

    user_a = User(
        username="p9-pos-a",
        email="p9-pos-a@test.com",
        password_hash="x",
    )
    user_b = User(
        username="p9-pos-b",
        email="p9-pos-b@test.com",
        password_hash="x",
    )
    session.add_all([user_a, user_b])
    await session.commit()

    member_a = Membership(
        workspace_id=workspace.id,
        user_id=user_a.id,
        instance_id=None,
        posx=42,
        posy=-17,
    )
    session.add(member_a)
    await session.commit()

    member_b = Membership(
        workspace_id=workspace.id,
        user_id=user_b.id,
        instance_id=None,
        posx=42,  # same as member_a
        posy=-17,  # same as member_a
    )
    session.add(member_b)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_unique_pos_constraint_allows_soft_deleted_overlap(
    session: AsyncSession, namespace_factory,
) -> None:
    """A soft-deleted membership at (5,5) does NOT block a new active
    membership at the same coords. Partial index excludes
    ``deleted_at IS NULL`` filter; matches Eyot soft-delete pattern.
    """
    ns = await namespace_factory()
    workspace = Workspace(namespace_id=ns.id, name="SoftDel Pos Workspace", slug="softdel-pos-workspace")
    session.add(workspace)
    await session.commit()

    user_a = User(username="p9-pos-c", email="p9-pos-c@test.com", password_hash="x")
    user_b = User(username="p9-pos-d", email="p9-pos-d@test.com", password_hash="x")
    session.add_all([user_a, user_b])
    await session.commit()

    old = Membership(
        workspace_id=workspace.id,
        user_id=user_a.id,
        instance_id=None,
        posx=5,
        posy=5,
    )
    session.add(old)
    await session.commit()
    old.soft_delete()
    await session.commit()

    new = Membership(
        workspace_id=workspace.id,
        user_id=user_b.id,
        instance_id=None,
        posx=5,
        posy=5,
    )
    session.add(new)
    # Should commit cleanly — partial unique index excludes soft-deleted.
    await session.commit()
    await session.refresh(new)
    assert new.id is not None


# ---------------------------------------------------------------------------
# 3. API-level 409 mapping (TestClient uses the conftest-managed DB)
# ---------------------------------------------------------------------------


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register_login_token(client: TestClient, username: str) -> str:
    """Register + login + return access_token."""
    client.post("/api/v1/auth/register", json={
        "username": username,
        "email": f"{username}@test.com",
        "password": "password123",
    })
    resp = client.post("/api/v1/auth/login", json={
        "username": username,
        "password": "password123",
    })
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def _user_id_by_username(session: AsyncSession, username: str) -> str:
    result = await session.execute(
        select(User).where(User.username == username),
    )
    user = result.scalars().first()
    assert user is not None, f"user {username!r} not in DB"
    return user.id


@pytest.mark.asyncio
async def test_api_create_membership_at_taken_pos_returns_409(
    client: TestClient,
    session: AsyncSession,
) -> None:
    """POST /messaging/memberships with a posx/posy already used by
    another active membership in the same workspace returns 409 with
    ``membership.position_taken`` error_code.
    """
    token_a = _register_login_token(client, "p9-pos-user-a")
    token_b = _register_login_token(client, "p9-pos-user-b")
    user_b_id = await _user_id_by_username(session, "p9-pos-user-b")
    h_a = _auth(token_a)
    h_b = _auth(token_b)

    workspace = client.post("/api/v1/workspaces", headers=h_a, json={
        "name": "API Dup Pos Workspace",
        "slug": "api-dup-pos",
    }).json()

    # P14b-onboard2: workspace creation auto-adds user_a as owner at (0, 0).
    # Patch user_a's auto-membership to occupy (10, 10) instead.
    list_resp = client.get(
        f"/api/v1/messaging/memberships?workspace_id={workspace['id']}",
        headers=h_a,
    )
    items = list_resp.json()["items"]
    assert len(items) == 1
    owner_membership_id = items[0]["id"]
    move_resp = client.patch(
        f"/api/v1/messaging/memberships/{owner_membership_id}",
        headers=h_a,
        json={"posx": 10, "posy": 10},
    )
    assert move_resp.status_code == 200, move_resp.json()

    # Second user joins at the SAME pos -> IntegrityError -> 409
    collision = client.post("/api/v1/messaging/memberships", headers=h_b, json={
        "workspace_id": workspace["id"],
        "user_id": user_b_id,
        "role": "viewer",
        "posx": 10,
        "posy": 10,
    })
    assert collision.status_code == 409, collision.json()
    assert collision.json()["error_code"] == "membership.position_taken"


@pytest.mark.asyncio
async def test_api_patch_membership_to_taken_pos_returns_409(
    client: TestClient,
    session: AsyncSession,
) -> None:
    """PATCH /messaging/memberships/{id} moving to a pos already
    occupied by another active membership returns 409.
    """
    token_a = _register_login_token(client, "p9-move-a")
    token_b = _register_login_token(client, "p9-move-b")
    user_b_id = await _user_id_by_username(session, "p9-move-b")
    h_a = _auth(token_a)
    h_b = _auth(token_b)

    workspace = client.post("/api/v1/workspaces", headers=h_a, json={
        "name": "Patch Move Workspace",
        "slug": "patch-move",
    }).json()

    # P14b-onboard2: user_a auto-joined as owner at (0, 0); look it up.
    list_resp = client.get(
        f"/api/v1/messaging/memberships?workspace_id={workspace['id']}",
        headers=h_a,
    )
    items = list_resp.json()["items"]
    assert len(items) == 1
    membership_a_id = items[0]["id"]

    client.post("/api/v1/messaging/memberships", headers=h_b, json={
        "workspace_id": workspace["id"],
        "user_id": user_b_id,
        "role": "viewer",
        "posx": 100,
        "posy": 100,
    })

    # Move A onto B's position -> 409
    resp = client.patch(
        f"/api/v1/messaging/memberships/{membership_a_id}",
        headers=h_a,
        json={"posx": 100, "posy": 100},
    )
    assert resp.status_code == 409, resp.json()
    assert resp.json()["error_code"] == "membership.position_taken"
