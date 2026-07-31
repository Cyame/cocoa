"""Topology cleanup: zombie passage soft-delete + entity delete gate."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def auth_token(client: TestClient) -> str:
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "topo_cleanup",
            "email": "topo_cleanup@test.com",
            "password": "password123",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "topo_cleanup", "password": "password123"},
    )
    return resp.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _default_ns(client: TestClient, token: str) -> dict:
    return client.get("/api/v1/namespaces", headers=_h(token)).json()["items"][0]


def _create_workspace(client: TestClient, token: str, *, slug: str) -> dict:
    ns = _default_ns(client, token)
    resp = client.post(
        "/api/v1/workspaces",
        headers=_h(token),
        json={"slug": slug, "name": slug, "namespace_id": ns["id"]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_entity(client: TestClient, token: str, *, slug: str) -> dict:
    ns = _default_ns(client, token)
    resp = client.post(
        "/api/v1/entities",
        headers=_h(token),
        json={
            "slug": slug,
            "name": f"Entity {slug}",
            "namespace_id": ns["id"],
            "rank": "intern",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _user_membership_id(client: TestClient, token: str, workspace_id: str) -> str:
    resp = client.get(
        f"/api/v1/messaging/memberships?workspace_id={workspace_id}&kind=user",
        headers=_h(token),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) >= 1
    return items[0]["id"]


class TestPassageCascadeOnNodeDelete:
    def test_delete_membership_soft_deletes_incident_passages(
        self, client: TestClient, auth_token: str
    ) -> None:
        ws = _create_workspace(client, auth_token, slug="ws-pass-cascade")
        entity = _create_entity(client, auth_token, slug="ent-pass-cascade")
        intro = client.post(
            f"/api/v1/workspaces/{ws['id']}/introduce-entity",
            headers=_h(auth_token),
            json={"entity_id": entity["id"]},
        )
        assert intro.status_code == 201, intro.text

        user_mem = _user_membership_id(client, auth_token, ws["id"])
        inst_mems = client.get(
            f"/api/v1/messaging/memberships?workspace_id={ws['id']}&kind=instance",
            headers=_h(auth_token),
        ).json()["items"]
        assert len(inst_mems) == 1
        inst_mem = inst_mems[0]["id"]

        passage = client.post(
            "/api/v1/messaging/passages",
            headers=_h(auth_token),
            json={
                "workspace_id": ws["id"],
                "from_membership_id": user_mem,
                "to_membership_id": inst_mem,
            },
        )
        assert passage.status_code == 201, passage.text
        passage_id = passage.json()["id"]

        deleted = client.delete(
            f"/api/v1/messaging/memberships/{inst_mem}",
            headers=_h(auth_token),
        )
        assert deleted.status_code == 204, deleted.text

        listed = client.get(
            f"/api/v1/messaging/passages?workspace_id={ws['id']}",
            headers=_h(auth_token),
        )
        assert listed.status_code == 200
        ids = {p["id"] for p in listed.json()["items"]}
        assert passage_id not in ids

    def test_delete_instance_soft_deletes_membership_and_passages(
        self, client: TestClient, auth_token: str
    ) -> None:
        ws = _create_workspace(client, auth_token, slug="ws-inst-cascade")
        entity = _create_entity(client, auth_token, slug="ent-inst-cascade")
        intro = client.post(
            f"/api/v1/workspaces/{ws['id']}/introduce-entity",
            headers=_h(auth_token),
            json={"entity_id": entity["id"]},
        )
        assert intro.status_code == 201, intro.text
        instance_id = intro.json()["id"]

        user_mem = _user_membership_id(client, auth_token, ws["id"])
        inst_mems = client.get(
            f"/api/v1/messaging/memberships?workspace_id={ws['id']}&kind=instance",
            headers=_h(auth_token),
        ).json()["items"]
        inst_mem = inst_mems[0]["id"]

        passage = client.post(
            "/api/v1/messaging/passages",
            headers=_h(auth_token),
            json={
                "workspace_id": ws["id"],
                "from_membership_id": user_mem,
                "to_membership_id": inst_mem,
            },
        )
        assert passage.status_code == 201, passage.text
        passage_id = passage.json()["id"]

        deleted = client.delete(
            f"/api/v1/instances/{instance_id}",
            headers=_h(auth_token),
        )
        assert deleted.status_code == 204, deleted.text

        mems = client.get(
            f"/api/v1/messaging/memberships?workspace_id={ws['id']}&kind=instance",
            headers=_h(auth_token),
        )
        assert mems.json()["total"] == 0

        passages = client.get(
            f"/api/v1/messaging/passages?workspace_id={ws['id']}",
            headers=_h(auth_token),
        )
        assert passage_id not in {p["id"] for p in passages.json()["items"]}


class TestEntityDeleteGate:
    def test_delete_entity_refuses_while_instance_active(
        self, client: TestClient, auth_token: str
    ) -> None:
        ws = _create_workspace(client, auth_token, slug="ws-ent-gate")
        entity = _create_entity(client, auth_token, slug="ent-gate")
        intro = client.post(
            f"/api/v1/workspaces/{ws['id']}/introduce-entity",
            headers=_h(auth_token),
            json={"entity_id": entity["id"]},
        )
        assert intro.status_code == 201, intro.text
        instance_id = intro.json()["id"]

        refused = client.delete(
            f"/api/v1/entities/{entity['id']}",
            headers=_h(auth_token),
        )
        assert refused.status_code == 409, refused.text
        body = refused.json()
        assert body["error_code"] == "entity.has_active_instances"
        assert body["message_key"] == "errors.entity.has_active_instances"
        assert instance_id in body["details"]["instance_ids"]

        exited = client.delete(
            f"/api/v1/instances/{instance_id}",
            headers=_h(auth_token),
        )
        assert exited.status_code == 204, exited.text

        deleted = client.delete(
            f"/api/v1/entities/{entity['id']}",
            headers=_h(auth_token),
        )
        assert deleted.status_code == 204, deleted.text

        gone = client.get(
            f"/api/v1/entities/{entity['id']}",
            headers=_h(auth_token),
        )
        assert gone.status_code == 404
