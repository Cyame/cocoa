"""Wave C PRD-v2 API happy-path tests."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def auth_token(client: TestClient) -> str:
    """First registered user is super-admin."""
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "wavec",
            "email": "wavec@test.com",
            "password": "password123",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "wavec", "password": "password123"},
    )
    return resp.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestOrganizations:
    def test_get_default_organization(self, client: TestClient, auth_token: str) -> None:
        resp = client.get("/api/v1/organizations/default", headers=_h(auth_token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["slug"] == "default"
        assert body["name"] == "Default World"

    def test_patch_default_organization(self, client: TestClient, auth_token: str) -> None:
        resp = client.patch(
            "/api/v1/organizations/default",
            headers=_h(auth_token),
            json={"name": "Renamed World"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed World"


class TestNamespaces:
    def test_list_namespaces_with_stats(
        self, client: TestClient, auth_token: str
    ) -> None:
        resp = client.get("/api/v1/namespaces", headers=_h(auth_token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        item = body["items"][0]
        assert "workspace_count" in item
        assert "entity_count" in item

    def test_create_namespace(self, client: TestClient, auth_token: str) -> None:
        resp = client.post(
            "/api/v1/namespaces",
            headers=_h(auth_token),
            json={"slug": "coding", "name": "Coding Scenario"},
        )
        assert resp.status_code == 201
        assert resp.json()["slug"] == "coding"


class TestNamespaceFilters:
    def test_workspaces_filter_by_namespace(
        self, client: TestClient, auth_token: str
    ) -> None:
        ns = client.get("/api/v1/namespaces", headers=_h(auth_token)).json()["items"][0]
        ws = client.post(
            "/api/v1/workspaces",
            headers=_h(auth_token),
            json={"slug": "filter-ws", "name": "Filter WS", "namespace_id": ns["id"]},
        )
        assert ws.status_code == 201
        resp = client.get(
            f"/api/v1/workspaces?namespace_id={ns['id']}",
            headers=_h(auth_token),
        )
        assert resp.status_code == 200
        slugs = {i["slug"] for i in resp.json()["items"]}
        assert "filter-ws" in slugs

    def test_entities_filter_by_namespace(
        self, client: TestClient, auth_token: str
    ) -> None:
        ns = client.get("/api/v1/namespaces", headers=_h(auth_token)).json()["items"][0]
        ent = client.post(
            "/api/v1/entities",
            headers=_h(auth_token),
            json={
                "slug": "filter-ent",
                "name": "Filter Entity",
                "namespace_id": ns["id"],
                "rank": "intern",
            },
        )
        assert ent.status_code == 201
        resp = client.get(
            f"/api/v1/entities?namespace_id={ns['id']}",
            headers=_h(auth_token),
        )
        assert resp.status_code == 200
        slugs = {i["slug"] for i in resp.json()["items"]}
        assert "filter-ent" in slugs


class TestUserGenes:
    def test_list_and_get_by_slug(self, client: TestClient, auth_token: str) -> None:
        listing = client.get("/api/v1/user-genes", headers=_h(auth_token))
        assert listing.status_code == 200
        assert listing.json()["total"] >= 16  # v4.0 atomic catalog
        resp = client.get(
            "/api/v1/user-genes/by-slug/can_view_workspace",
            headers=_h(auth_token),
        )
        assert resp.status_code == 200
        assert resp.json()["slug"] == "can_view_workspace"
        assert resp.json()["effect_scope"] == "workspace"

    def test_create_attach_detach(self, client: TestClient, auth_token: str) -> None:
        from app.core.config import settings
        from app.core.security import decode_token

        create = client.post(
            "/api/v1/user-genes",
            headers=_h(auth_token),
            json={
                "slug": "can_custom_flag",
                "name": "Custom",
                "effect_scope": "org",
            },
        )
        assert create.status_code == 201
        gene_id = create.json()["id"]
        user_id = decode_token(auth_token, settings.JWT_SECRET)["sub"]
        attach = client.post(
            f"/api/v1/user-genes/{gene_id}/attach",
            headers=_h(auth_token),
            json={"user_id": user_id},
        )
        assert attach.status_code == 201
        detach = client.delete(
            f"/api/v1/user-genes/{gene_id}/attach/{user_id}",
            headers=_h(auth_token),
        )
        assert detach.status_code == 204


class TestAiGenes:
    def test_crud_and_base_class_attach(
        self, client: TestClient, auth_token: str
    ) -> None:
        create = client.post(
            "/api/v1/ai-genes",
            headers=_h(auth_token),
            json={
                "slug": "test-gene",
                "name": "Test Gene",
                "manifest": {"tools": ["shell"]},
            },
        )
        assert create.status_code == 201
        gene_id = create.json()["id"]
        by_slug = client.get(
            "/api/v1/ai-genes/by-slug/test-gene",
            headers=_h(auth_token),
        )
        assert by_slug.status_code == 200
        bc = client.get("/api/v1/base-classes", headers=_h(auth_token)).json()["items"][0]
        attach = client.post(
            f"/api/v1/ai-genes/{gene_id}/attach-base-class",
            headers=_h(auth_token),
            json={"base_class_id": bc["id"]},
        )
        assert attach.status_code == 201
        assert attach.json()["status"] == "attached"


class TestBaseClassBySlug:
    def test_get_by_slug(self, client: TestClient, auth_token: str) -> None:
        resp = client.get("/api/v1/base-classes/mi-shi", headers=_h(auth_token))
        assert resp.status_code == 200
        assert resp.json()["slug"] == "mi-shi"


class TestCapabilityMarket:
    def test_list_capability_market(
        self, client: TestClient, auth_token: str
    ) -> None:
        resp = client.get(
            "/api/v1/learning/capability-market?type=skill",
            headers=_h(auth_token),
        )
        assert resp.status_code == 200
        assert "items" in resp.json()


class TestBrainRegions:
    def _workspace_id(self, client: TestClient, token: str) -> str:
        resp = client.post(
            "/api/v1/workspaces",
            headers=_h(token),
            json={"slug": "brain-ws", "name": "Brain WS"},
        )
        return resp.json()["id"]

    def test_frontal_brainstem_cerebellum(
        self, client: TestClient, auth_token: str
    ) -> None:
        wid = self._workspace_id(client, auth_token)
        kanban = client.post(
            f"/api/v1/central-hubs/{wid}/frontal-lobe/kanbans",
            headers=_h(auth_token),
            json={"title": "Task A", "position": 0},
        )
        assert kanban.status_code == 201
        schedule = client.post(
            f"/api/v1/central-hubs/{wid}/brainstem/schedules",
            headers=_h(auth_token),
            json={"name": "daily", "cron_expr": "0 9 * * *"},
        )
        assert schedule.status_code == 201
        cerebellum = client.get(
            f"/api/v1/central-hubs/{wid}/cerebellum",
            headers=_h(auth_token),
        )
        assert cerebellum.status_code == 200
        restart = client.post(
            f"/api/v1/central-hubs/{wid}/cerebellum/restart",
            headers=_h(auth_token),
        )
        assert restart.status_code == 200
        assert restart.json()["loop_status"] == "idle"


class TestInstanceOverlay:
    def test_create_instance_resolves_agent_config(
        self, client: TestClient, auth_token: str
    ) -> None:
        bc = client.post(
            "/api/v1/base-classes",
            headers=_h(auth_token),
            json={
                "slug": "overlay-bc",
                "name": "Overlay BC",
                "manifest": {
                    "system_prompt": "Base prompt",
                    "default_model": "gpt-4o-mini",
                    "commands": ["status"],
                },
            },
        )
        assert bc.status_code == 201
        ns = client.get("/api/v1/namespaces", headers=_h(auth_token)).json()["items"][0]
        ent = client.post(
            "/api/v1/entities",
            headers=_h(auth_token),
            json={
                "slug": "overlay-ent",
                "name": "Overlay Entity",
                "namespace_id": ns["id"],
                "rank": "intern",
                "preset_slug": "overlay-bc",
                "system_prompt": "Entity overlay prompt",
                "config_override": {"default_model": "gpt-4o"},
            },
        )
        assert ent.status_code == 201
        ws = client.post(
            "/api/v1/workspaces",
            headers=_h(auth_token),
            json={"slug": "overlay-ws", "name": "Overlay WS", "namespace_id": ns["id"]},
        )
        assert ws.status_code == 201
        inst = client.post(
            "/api/v1/instances",
            headers=_h(auth_token),
            json={
                "entity_id": ent.json()["id"],
                "workspace_id": ws.json()["id"],
            },
        )
        assert inst.status_code == 201
        cfg = inst.json()["runtime_config"]["agent_config"]
        assert cfg["system_prompt"] == "Entity overlay prompt"
        assert cfg["default_model"] == "gpt-4o"
        # Capabilities are Entity-authoritative (empty entity → empty, not BaseClass union).
        assert cfg["default_capabilities"] == []
        assert cfg["default_gene_refs"] == []
