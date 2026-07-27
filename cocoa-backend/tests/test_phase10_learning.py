"""Integration tests for P10 Wave 2 Learning API endpoints.

Covers:
- GET  /api/v1/learning/memories/{employee_id}/summary  (summary)
- POST /api/v1/learning/employees/{employee_id}/distill  (distillation)
- GET  /api/v1/learning/presets/{preset_id}              (preset fetch)
- P5  directive_router learning command branch            (route_turn)
"""

import uuid

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
    """Register and login a throwaway user."""
    client.post("/api/v1/auth/register", json={
        "username": "learning_test",
        "email": "learning_test@test.com",
        "password": "password123",
    })
    resp = client.post("/api/v1/auth/login", json={
        "username": "learning_test",
        "password": "password123",
    })
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def auth_user_id(auth_token: str, session: AsyncSession) -> str:
    """Return the UUID of the auth_token user."""
    result = await session.execute(
        select(User).where(User.username == "learning_test"),
    )
    user: User = result.scalars().first()
    return user.id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup_office_and_membership(
    client: TestClient,
    token: str,
    user_id: str,
    office_name: str = "Learning Office",
    office_slug: str = "learning-office",
    role: str = "owner",
) -> str:
    """Create an office and add *user_id* as member with *role*. Returns office_id."""
    h = _auth(token)
    resp = client.post("/api/v1/offices", headers=h, json={
        "name": office_name,
        "slug": office_slug,
    })
    assert resp.status_code == 201, resp.text
    office_id = resp.json()["id"]

    resp = client.post("/api/v1/messaging/memberships", headers=h, json={
        "office_id": office_id,
        "user_id": user_id,
        "role": role,
    })
    assert resp.status_code == 201, resp.text
    return office_id


def _create_employee(client: TestClient, token: str, slug: str, name: str) -> str:
    """Create an employee and return its UUID."""
    resp = client.post("/api/v1/employees", headers=_auth(token), json={
        "name": name,
        "slug": slug,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_instance(
    client: TestClient,
    token: str,
    employee_id: str,
    office_id: str,
) -> str:
    """Create an instance and return its UUID."""
    resp = client.post("/api/v1/instances", headers=_auth(token), json={
        "employee_id": employee_id,
        "office_id": office_id,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_memory(
    client: TestClient,
    token: str,
    employee_id: str,
    *,
    kind: str,
    key: str | None = None,
    content: str | None = None,
) -> str:
    """Create a memory entry and return its UUID."""
    body: dict = {
        "employee_id": employee_id,
        "kind": kind,
    }
    if key is not None:
        body["key"] = key
    if content is not None:
        body["content"] = content
    resp = client.post("/api/v1/memory/entries", headers=_auth(token), json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# =========================================================================
# GET /learning/memories/{employee_id}/summary
# =========================================================================


class TestMemorySummary:
    """Tests for the memory summary endpoint."""

    def test_summary_with_memories(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        """GET summary returns correct counts when memories exist."""
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="Summary Office", office_slug=f"summary-office-{uuid.uuid4().hex[:6]}",
        )
        employee_id = _create_employee(
            client, auth_token, f"summary-emp-{uuid.uuid4().hex[:6]}", "Summary Employee",
        )
        _create_instance(client, auth_token, employee_id, office_id)

        # Create 2 experience, 3 lesson, 1 decision, 1 problem memories.
        for i in range(2):
            _create_memory(client, auth_token, employee_id, kind="experience",
                           key=f"exp-key-{i}", content=f"Experience {i} content")
        for i in range(3):
            _create_memory(client, auth_token, employee_id, kind="lesson",
                           key=f"lesson-key-{i}", content=f"Lesson {i} is a great insight about coding")
        _create_memory(client, auth_token, employee_id, kind="decision",
                       key="decide-stack", content="We decided to use FastAPI")
        _create_memory(client, auth_token, employee_id, kind="problem",
                       key="bug-oom", content="Out of memory error occurred")

        resp = client.get(
            f"/api/v1/learning/memories/{employee_id}/summary",
            headers=h,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["employee_id"] == employee_id
        counts = body["aggregated_counts"]
        assert counts["experience"] == 2
        assert counts["lesson"] == 3
        assert counts["decision"] == 1
        assert counts["problem"] == 1
        assert counts["total"] == 7
        assert len(body["sample_lessons"]) > 0
        assert "lesson" in body["sample_keys_by_kind"]

    def test_summary_with_kind_filter(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        """GET summary with kind filter returns only matching kinds."""
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="Filter Office", office_slug=f"filter-office-{uuid.uuid4().hex[:6]}",
        )
        employee_id = _create_employee(
            client, auth_token, f"filter-emp-{uuid.uuid4().hex[:6]}", "Filter Employee",
        )
        _create_instance(client, auth_token, employee_id, office_id)

        _create_memory(client, auth_token, employee_id, kind="experience",
                       key="exp", content="Experience content")
        _create_memory(client, auth_token, employee_id, kind="lesson",
                       key="lesson", content="A valuable lesson learned")
        _create_memory(client, auth_token, employee_id, kind="decision",
                       key="dec", content="Made a decision")

        resp = client.get(
            f"/api/v1/learning/memories/{employee_id}/summary",
            headers=h,
            params={"kind": ["experience", "lesson"]},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        counts = body["aggregated_counts"]
        assert counts["experience"] == 1
        assert counts["lesson"] == 1
        assert counts["decision"] == 0
        assert counts["problem"] == 0
        assert counts["total"] == 2
        # sample_keys_by_kind should only contain filtered kinds
        assert "decision" not in body["sample_keys_by_kind"]

    def test_summary_nonexistent_employee(
        self,
        client: TestClient,
        auth_token: str,
    ) -> None:
        """GET summary with a nonexistent employee ID returns 404."""
        h = _auth(auth_token)
        fake_id = str(uuid.uuid4())
        resp = client.get(
            f"/api/v1/learning/memories/{fake_id}/summary",
            headers=h,
        )
        assert resp.status_code == 404, resp.text

    def test_summary_employee_no_office(
        self,
        client: TestClient,
        auth_token: str,
    ) -> None:
        """GET summary for an employee with no instance (no office) returns 404."""
        h = _auth(auth_token)
        employee_id = _create_employee(
            client, auth_token, f"no-office-{uuid.uuid4().hex[:6]}", "No Office Employee",
        )
        # No instance created — employee has no office association.
        resp = client.get(
            f"/api/v1/learning/memories/{employee_id}/summary",
            headers=h,
        )
        assert resp.status_code == 404, resp.text


# =========================================================================
# POST /learning/employees/{employee_id}/distill
# =========================================================================


class TestDistill:
    """Tests for the distillation endpoint."""

    def test_distill_creates_preset(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        """POST distill creates a new EmployeePreset with 201 and correct fields."""
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="Distill Office", office_slug=f"distill-office-{uuid.uuid4().hex[:6]}",
        )
        employee_id = _create_employee(
            client, auth_token, f"distill-emp-{uuid.uuid4().hex[:6]}", "Distill Employee",
        )
        _create_instance(client, auth_token, employee_id, office_id)

        # Create memories with enough data for distillation.
        _create_memory(client, auth_token, employee_id, kind="experience",
                       key="exp", content="Experience content")
        _create_memory(client, auth_token, employee_id, kind="lesson",
                       key="debug-memory-leak",
                       content="A" * 80 + " We found that memory leaks happen"
                               " when circular references are not broken.")
        _create_memory(client, auth_token, employee_id, kind="decision",
                       key="pick-framework", content="Decided to use FastAPI over Flask")

        resp = client.post(
            f"/api/v1/learning/employees/{employee_id}/distill",
            headers=h,
            json={
                "target_skill_slug": "my-skill",
                "target_preset_name": "My Distilled Skill",
                "memory_kind_filter": None,
                "source_preset_slug": None,
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()

        assert body["new_preset_id"]
        assert body["new_preset_slug"] == "base-skill-my-skill"
        assert body["new_preset_name"] == "My Distilled Skill"
        assert body["source_employee_id"] == employee_id
        assert body["source_preset_slug"] is None

        manifest = body["manifest_preview"]
        assert manifest["model"] == "tbd"
        assert len(manifest["prompt"]) > 0
        assert "debug-memory-leak" in manifest["commands"] or "pick-framework" in manifest["commands"]
        assert manifest["tools"] == []

        aggregated = body["aggregated_memory"]
        assert aggregated["total"] == 3

    def test_distill_slug_conflict(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        """POST distill returns 409 when the generated slug already exists."""
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="Conflict Office", office_slug=f"conflict-office-{uuid.uuid4().hex[:6]}",
        )
        employee_id = _create_employee(
            client, auth_token, f"conflict-emp-{uuid.uuid4().hex[:6]}", "Conflict Employee",
        )
        _create_instance(client, auth_token, employee_id, office_id)

        _create_memory(client, auth_token, employee_id, kind="lesson",
                       key="some-lesson", content="A" * 60)

        # First distillation.
        resp1 = client.post(
            f"/api/v1/learning/employees/{employee_id}/distill",
            headers=h,
            json={"target_skill_slug": "my-skill"},
        )
        assert resp1.status_code == 201, resp1.text

        # Second distillation with same target_skill_slug → same generated slug.
        resp2 = client.post(
            f"/api/v1/learning/employees/{employee_id}/distill",
            headers=h,
            json={"target_skill_slug": "my-skill"},
        )
        assert resp2.status_code == 409, resp2.text
        body = resp2.json()
        assert body["error_code"] == "employee_preset.slug_taken"

    def test_distill_no_memory(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        """POST distill returns 422 when employee has no memory entries."""
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="NoMem Office", office_slug=f"nomem-office-{uuid.uuid4().hex[:6]}",
        )
        employee_id = _create_employee(
            client, auth_token, f"nomem-emp-{uuid.uuid4().hex[:6]}", "No Memory Employee",
        )
        _create_instance(client, auth_token, employee_id, office_id)

        resp = client.post(
            f"/api/v1/learning/employees/{employee_id}/distill",
            headers=h,
            json={"target_skill_slug": "foo-bar"},
        )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["error_code"] == "learning.no_memory"

    @pytest.mark.asyncio
    async def test_distill_viewer_forbidden(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """POST distill as a viewer returns 403."""
        h_owner = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="Viewer Office", office_slug=f"viewer-office-{uuid.uuid4().hex[:6]}",
            role="owner",
        )
        employee_id = _create_employee(
            client, auth_token, f"viewer-emp-{uuid.uuid4().hex[:6]}", "Viewer Employee",
        )
        _create_instance(client, auth_token, employee_id, office_id)
        _create_memory(client, auth_token, employee_id, kind="lesson",
                       key="lesson-key", content="A" * 60)

        viewer_username = f"distill-viewer-{uuid.uuid4().hex[:6]}"
        client.post("/api/v1/auth/register", json={
            "username": viewer_username,
            "email": f"{viewer_username}@test.com",
            "password": "password123",
        })
        viewer_login = client.post("/api/v1/auth/login", json={
            "username": viewer_username,
            "password": "password123",
        })
        viewer_token = viewer_login.json()["access_token"]

        result = await session.execute(
            select(User).where(User.username == viewer_username)
        )
        viewer_user: User = result.scalars().first()

        client.post("/api/v1/messaging/memberships", headers=h_owner, json={
            "office_id": office_id,
            "user_id": viewer_user.id,
            "role": "viewer",
        })

        resp = client.post(
            f"/api/v1/learning/employees/{employee_id}/distill",
            headers=_auth(viewer_token),
            json={"target_skill_slug": "forbidden-skill"},
        )
        assert resp.status_code == 403, resp.text

    def test_distill_nonexistent_employee(
        self,
        client: TestClient,
        auth_token: str,
    ) -> None:
        """POST distill with a nonexistent employee ID returns 404."""
        h = _auth(auth_token)
        fake_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/v1/learning/employees/{fake_id}/distill",
            headers=h,
            json={"target_skill_slug": "ghost-skill"},
        )
        assert resp.status_code == 404, resp.text


# =========================================================================
# GET /learning/presets/{preset_id}
# =========================================================================


class TestPresetFetch:
    """Tests for the preset fetch endpoint."""

    def test_fetch_preset(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
    ) -> None:
        """GET /learning/presets/{preset_id} returns 200 with manifest."""
        h = _auth(auth_token)
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="Fetch Office", office_slug=f"fetch-office-{uuid.uuid4().hex[:6]}",
        )
        employee_id = _create_employee(
            client, auth_token, f"fetch-emp-{uuid.uuid4().hex[:6]}", "Fetch Employee",
        )
        _create_instance(client, auth_token, employee_id, office_id)
        _create_memory(client, auth_token, employee_id, kind="lesson",
                       key="fetch-lesson", content="B" * 60)

        # First distill to create a preset.
        distill_resp = client.post(
            f"/api/v1/learning/employees/{employee_id}/distill",
            headers=h,
            json={"target_skill_slug": "fetch-skill", "target_preset_name": "Fetch Skill"},
        )
        assert distill_resp.status_code == 201, distill_resp.text
        preset_id = distill_resp.json()["new_preset_id"]

        # Now fetch it.
        resp = client.get(
            f"/api/v1/learning/presets/{preset_id}",
            headers=h,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["new_preset_id"] == preset_id
        assert body["new_preset_slug"] == "base-skill-fetch-skill"
        assert body["new_preset_name"] == "Fetch Skill"
        manifest = body["manifest_preview"]
        assert "model" in manifest
        assert body["aggregated_memory"]["total"] == 0  # GET preset fetch returns empty aggregated

    def test_fetch_preset_not_found(
        self,
        client: TestClient,
        auth_token: str,
    ) -> None:
        """GET /learning/presets/{preset_id} with a nonexistent ID returns 404."""
        h = _auth(auth_token)
        fake_id = str(uuid.uuid4())
        resp = client.get(
            f"/api/v1/learning/presets/{fake_id}",
            headers=h,
        )
        assert resp.status_code == 404, resp.text


# =========================================================================
# P5 directive_router learning command branch
# =========================================================================


class TestP5RouteTurnLearningBranch:
    """Verify that learning commands are correctly routed by the P5 directive router."""

    @pytest.mark.asyncio
    async def test_route_turn_distill_creates_preset(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """@target /distill creates new EmployeePreset and emits LEARNING_DISTILLATION_COMPLETED."""
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="RT Distill Office",
            office_slug=f"rt-distill-office-{uuid.uuid4().hex[:6]}",
        )
        employee_slug = f"rt-distill-emp-{uuid.uuid4().hex[:6]}"
        employee_id = _create_employee(
            client, auth_token, employee_slug, "RT Distill Employee",
        )
        _create_instance(client, auth_token, employee_id, office_id)

        _create_memory(client, auth_token, employee_id, kind="lesson",
                       key="debug-memory-leak",
                       content="A" * 80 + " We found that memory leaks happen"
                                " when circular references are not broken.")
        _create_memory(client, auth_token, employee_id, kind="experience",
                       key="first-exp", content="Worked on a big project.")

        from app.core.directive_router import route_turn
        from app.core.event_types import LEARNING_DISTILLATION_COMPLETED
        from app.models.employee import EmployeePreset
        from app.models.event import Event

        raw_text = f"@{employee_slug} /distill my-skill"
        results = await route_turn(session, raw_text, office_id, auth_user_id)

        assert len(results) == 1
        assert results[0].cmd == "/distill"
        assert results[0].target_employee == employee_slug

        preset_result = await session.execute(
            select(EmployeePreset).where(
                EmployeePreset.slug == "base-skill-my-skill",
                EmployeePreset.deleted_at.is_(None),
            )
        )
        preset = preset_result.scalars().first()
        assert preset is not None, "Expected new EmployeePreset for base-skill-my-skill"
        assert preset.name == "Skill: my-skill"
        assert preset.manifest is not None
        assert isinstance(preset.manifest, dict)

        event_result = await session.execute(
            select(Event).where(
                Event.type == LEARNING_DISTILLATION_COMPLETED,
                Event.resource_id == preset.id,
            )
        )
        event = event_result.scalars().first()
        assert event is not None, "Expected LEARNING_DISTILLATION_COMPLETED event"
        assert event.payload["employee_id"] == employee_id

    @pytest.mark.asyncio
    async def test_route_turn_bare_distill_dropped(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """Bare /distill (no @target) is silently dropped."""
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="RT Bare Distill Office",
            office_slug=f"rt-bare-distill-{uuid.uuid4().hex[:6]}",
        )

        from app.core.directive_router import route_turn

        raw_text = "/distill"
        results = await route_turn(session, raw_text, office_id, auth_user_id)

        assert len(results) == 1
        assert results[0].cmd == "/distill"
        assert results[0].target_employee is None

    @pytest.mark.asyncio
    async def test_route_turn_learning_vs_control_no_conflict(
        self,
        client: TestClient,
        auth_token: str,
        auth_user_id: str,
        session: AsyncSession,
    ) -> None:
        """/distill does not conflict with /interrupt — both route to separate branches."""
        office_id = _setup_office_and_membership(
            client, auth_token, auth_user_id,
            office_name="RT NoConflict Office",
            office_slug=f"rt-noconflict-{uuid.uuid4().hex[:6]}",
        )
        employee_slug = f"rt-noconflict-emp-{uuid.uuid4().hex[:6]}"
        employee_id = _create_employee(
            client, auth_token, employee_slug, "RT NoConflict Employee",
        )
        _create_instance(client, auth_token, employee_id, office_id)

        _create_memory(client, auth_token, employee_id, kind="lesson",
                       key="debug-memory-leak",
                       content="A" * 80 + " We found that memory leaks happen"
                                " when circular references are not broken.")

        from app.core.directive_router import route_turn
        from app.core.preset_registry import is_control_command, is_learning_command

        distill_text = f"@{employee_slug} /distill test-skill"
        distill_results = await route_turn(session, distill_text, office_id, auth_user_id)
        assert len(distill_results) == 1
        assert distill_results[0].cmd == "/distill"

        assert is_learning_command("/distill") is True
        assert is_control_command("/distill") is False
        assert is_learning_command("/interrupt") is False
        assert is_control_command("/interrupt") is True
