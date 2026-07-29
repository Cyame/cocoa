"""Tests for P9 Todo 4 — ``GET /api/v1/base-classes/{slug}`` detail endpoint.

Verifies the slug-based detail endpoint expands the JSONB ``manifest`` into
the 5-field :class:`PresetManifestOut` schema and returns 404 for missing
or soft-deleted presets.
"""

from __future__ import annotations

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


_MANIFEST_FIELDS = ("model", "prompt", "skills", "tools", "commands")


class TestGetPresetBySlug:
    """``GET /api/v1/base-classes/{slug}`` detail endpoint."""

    def test_get_builtin_preset_returns_expanded_manifest(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """Built-in ``mi-shi`` preset returns 200 with a 5-field manifest."""
        resp = client.get(
            "/api/v1/base-classes/mi-shi",
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["slug"] == "mi-shi"
        assert body["name"] == "密士"
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
        """``mi-shi`` (密士) commands list is non-empty per builtin_presets spec."""
        resp = client.get(
            "/api/v1/base-classes/mi-shi",
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
        self, client: TestClient, auth_token: str, session: AsyncSession,
    ) -> None:
        """Soft-deleting a preset makes its slug return 404."""
        # Create a custom preset, then soft-delete it.
        create_resp = client.post(
            "/api/v1/base-classes",
            headers=_auth_headers(auth_token),
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
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "base_class.not_found"


class TestGetPresetManifestExpansion:
    """Manifest expansion behaviour."""

    def test_preset_without_manifest_still_returns_5_fields(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """A preset with ``manifest=None`` still serialises 5 manifest fields via defaults."""
        # Create a preset with no manifest.
        client.post(
            "/api/v1/base-classes",
            headers=_auth_headers(auth_token),
            json={"slug": "no-manifest", "name": "No Manifest"},
        )

        resp = client.get(
            "/api/v1/base-classes/no-manifest",
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 200
        manifest = resp.json()["manifest"]
        for field in _MANIFEST_FIELDS:
            assert field in manifest
        # Defaults from PresetManifest.
        assert manifest["model"] == "tbd"
        assert manifest["prompt"] == "TODO P8"
        assert manifest["skills"] == []
        assert manifest["tools"] == []
        assert manifest["commands"] == []

    def test_preset_with_partial_manifest_fills_defaults(
        self, client: TestClient, auth_token: str,
    ) -> None:
        """A manifest with only some keys fills the rest from defaults."""
        client.post(
            "/api/v1/base-classes",
            headers=_auth_headers(auth_token),
            json={
                "slug": "partial-manifest",
                "name": "Partial",
                "manifest": {"model": "claude-3", "commands": ["run"]},
            },
        )

        resp = client.get(
            "/api/v1/base-classes/partial-manifest",
            headers=_auth_headers(auth_token),
        )
        assert resp.status_code == 200
        manifest = resp.json()["manifest"]
        assert manifest["model"] == "claude-3"
        assert manifest["commands"] == ["run"]
        # Defaults for unfilled fields.
        assert manifest["prompt"] == "TODO P8"
        assert manifest["skills"] == []
        assert manifest["tools"] == []

    def test_unauthenticated_request_returns_401(
        self, client: TestClient,
    ) -> None:
        """GET without an auth token is rejected (CurrentUserDep enforced)."""
        resp = client.get("/api/v1/base-classes/mi-shi")
        assert resp.status_code == 401
