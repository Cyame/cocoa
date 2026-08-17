"""Tests for P9 Todo 4 — ``GET /api/v1/base-classes/{slug}`` detail endpoint.

Verifies the slug-based detail endpoint expands the JSONB ``manifest`` into
the 5-field :class:`PresetManifestOut` schema and returns 404 for missing
or soft-deleted presets.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

from app.models.base_class import BaseClass


@pytest.fixture
def auth_token(client: TestClient) -> str:
    """Register and login a throwaway user, return access token."""
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "presetdetail",
            "email": "presetdetail@test.com",
            "password": "password123",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "presetdetail", "password": "password123"},
    )
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(client: TestClient, username: str, email: str) -> tuple[str, str]:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": email,
            "password": "password123",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["id"]


_MANIFEST_FIELDS = ("model", "prompt", "skills", "tools", "commands")


class TestGetPresetBySlug:
    """``GET /api/v1/base-classes/{slug}`` detail endpoint."""

    def test_get_builtin_preset_returns_expanded_manifest(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """Built-in ``fox`` preset returns 200 with a 5-field manifest."""
        resp = client.get(
            "/api/v1/base-classes/fox",
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["slug"] == "fox"
        assert body["name"] == "狐狸"
        assert "id" in body
        assert "created_at" in body
        assert "updated_at" in body
        assert "version" in body

        # Manifest is expanded into 5 typed fields.
        manifest = body["manifest"]
        assert isinstance(manifest, dict)
        for field in _MANIFEST_FIELDS:
            assert field in manifest, f"manifest missing field {field!r}"
        assert isinstance(manifest["skills"], list)
        assert isinstance(manifest["tools"], list)
        assert isinstance(manifest["commands"], list)

    def test_get_builtin_preset_has_commands(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """``fox`` (狐狸) commands list is non-empty per builtin_presets spec."""
        resp = client.get(
            "/api/v1/base-classes/fox",
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 200
        commands = resp.json()["manifest"]["commands"]
        assert len(commands) > 0
        assert "plan" in commands
        assert "decompose" in commands
        assert "prioritize" in commands

    def test_get_nonexistent_slug_returns_404(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """A slug that doesn't exist returns 404 with the expected error code."""
        resp = client.get(
            "/api/v1/base-classes/does-not-exist",
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["error_code"] == "base_class.not_found"

    @pytest.mark.asyncio
    async def test_get_soft_deleted_slug_returns_404(
        self, client: TestClient, session: AsyncSession, create_org_bundle,
    ) -> None:
        """Soft-deleting a preset makes its slug return 404."""
        # Register an org-scoped user (v4.1 D15: org rows need an org context).
        token, user_id = _register(
            client, f"pd-{uuid.uuid4().hex[:6]}", f"pd-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle = await create_org_bundle(user_id, atoms=("can_manage_organization",))
        headers = {**_auth_headers(token), "X-Organization-Id": bundle.org.id}

        # Create a custom preset, then soft-delete it.
        create_resp = client.post(
            "/api/v1/base-classes",
            headers=headers,
            json={
                "slug": "to-soft-delete",
                "name": "Soft Delete Me",
                "manifest": {
                    "model": "gpt-4o",
                    "prompt": "You are x.",
                    "skills": ["a"],
                    "tools": ["b"],
                    "commands": ["c"],
                },
            },
        )
        assert create_resp.status_code == 201
        preset_id = create_resp.json()["id"]

        # Soft-delete via the session directly (faster than DELETE endpoint).
        preset = await session.get(BaseClass, preset_id)
        assert preset is not None
        preset.soft_delete()
        await session.commit()

        resp = client.get(
            "/api/v1/base-classes/to-soft-delete",
            headers=headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "base_class.not_found"


class TestGetPresetManifestExpansion:
    """Manifest expansion behaviour."""

    @pytest.mark.asyncio
    async def test_preset_without_manifest_returns_mirror_arrays(
        self, client: TestClient, session: AsyncSession, create_org_bundle,
    ) -> None:
        """v4.0: the response manifest carries junction-filled mirror arrays
        (``skills``/``tools``/``commands``) even when ``manifest=None``."""
        token, user_id = _register(
            client, f"pd-{uuid.uuid4().hex[:6]}", f"pd-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle = await create_org_bundle(user_id, atoms=("can_manage_organization",))
        headers = {**_auth_headers(token), "X-Organization-Id": bundle.org.id}

        # Create a preset with no manifest.
        client.post(
            "/api/v1/base-classes",
            headers=headers,
            json={"slug": "no-manifest", "name": "No Manifest"},
        )

        resp = client.get(
            "/api/v1/base-classes/no-manifest",
            headers=headers,
        )
        assert resp.status_code == 200
        manifest = resp.json()["manifest"]
        assert manifest["skills"] == []
        assert manifest["tools"] == []
        assert manifest["commands"] == []

    @pytest.mark.asyncio
    async def test_preset_with_partial_manifest_mirror_from_junction(
        self, client: TestClient, session: AsyncSession, create_org_bundle,
    ) -> None:
        """v4.0: other manifest keys pass through; mirror arrays come from
        junction rows (``commands`` in the write payload is stripped)."""
        token, user_id = _register(
            client, f"pd-{uuid.uuid4().hex[:6]}", f"pd-{uuid.uuid4().hex[:6]}@t.co"
        )
        bundle = await create_org_bundle(user_id, atoms=("can_manage_organization",))
        headers = {**_auth_headers(token), "X-Organization-Id": bundle.org.id}

        client.post(
            "/api/v1/base-classes",
            headers=headers,
            json={
                "slug": "partial-manifest",
                "name": "Partial",
                "manifest": {"model": "claude-3", "commands": ["run"]},
            },
        )

        resp = client.get(
            "/api/v1/base-classes/partial-manifest",
            headers=headers,
        )
        assert resp.status_code == 200
        manifest = resp.json()["manifest"]
        assert manifest["model"] == "claude-3"
        # Write-path strip + empty junction → empty mirror.
        assert manifest["commands"] == []
        assert manifest["skills"] == []
        assert manifest["tools"] == []

    def test_builtin_preset_commands_mirrored_from_junction(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """v4.0: builtin presets expose their commands via the cmd-* junction."""
        resp = client.get(
            "/api/v1/base-classes/fox",
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 200
        manifest = resp.json()["manifest"]
        assert sorted(manifest["commands"]) == ["decompose", "plan", "prioritize"]

    def test_unauthenticated_request_returns_401(
        self, client: TestClient,
    ) -> None:
        """GET without an auth token is rejected (CurrentUserDep enforced)."""
        resp = client.get("/api/v1/base-classes/fox")
        assert resp.status_code == 401
