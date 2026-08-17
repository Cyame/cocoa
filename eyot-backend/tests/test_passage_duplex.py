"""Duplex Passage neighbor + mention-candidates + membership username enrich."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def auth_token(client: TestClient) -> str:
    client.post(
        "/api/v1/auth/register",
        json={
            "username": "duplex_user",
            "email": "duplex_user@test.com",
            "password": "password123",
        },
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "duplex_user", "password": "password123"},
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


class TestDuplexPassageMentions:
    def test_reverse_passage_appears_in_mention_candidates(
        self, client: TestClient, auth_token: str
    ) -> None:
        ws = _create_workspace(client, auth_token, slug="ws-duplex-mention")
        entity = _create_entity(client, auth_token, slug="ent-duplex-mention")
        intro = client.post(
            f"/api/v1/workspaces/{ws['id']}/introduce-entity",
            headers=_h(auth_token),
            json={"entity_id": entity["id"]},
        )
        assert intro.status_code == 201, intro.text

        user_mem = client.get(
            f"/api/v1/messaging/memberships?workspace_id={ws['id']}&kind=user",
            headers=_h(auth_token),
        ).json()["items"][0]
        assert user_mem["username"] == "duplex_user"

        inst_mem = client.get(
            f"/api/v1/messaging/memberships?workspace_id={ws['id']}&kind=instance",
            headers=_h(auth_token),
        ).json()["items"][0]

        # Reverse orientation: Lost One → User (click order)
        passage = client.post(
            "/api/v1/messaging/passages",
            headers=_h(auth_token),
            json={
                "workspace_id": ws["id"],
                "from_membership_id": inst_mem["id"],
                "to_membership_id": user_mem["id"],
            },
        )
        assert passage.status_code == 201, passage.text
        body = passage.json()
        lo, hi = sorted([inst_mem["id"], user_mem["id"]])
        assert body["from_membership_id"] == lo
        assert body["to_membership_id"] == hi
        assert body["mode"] == "dual"

        # Opposite click order is the same undirected edge → 409
        again = client.post(
            "/api/v1/messaging/passages",
            headers=_h(auth_token),
            json={
                "workspace_id": ws["id"],
                "from_membership_id": user_mem["id"],
                "to_membership_id": inst_mem["id"],
            },
        )
        assert again.status_code == 409, again.text
        assert again.json()["error_code"] == "passage.duplicate"

        cands = client.get(
            f"/api/v1/workspaces/{ws['id']}/mention-candidates",
            headers=_h(auth_token),
        )
        assert cands.status_code == 200, cands.text
        body = cands.json()
        assert body["total"] == 1
        assert body["items"][0]["slug"] == "ent-duplex-mention"
        assert body["items"][0]["connected"] is True


class TestUndirectedAcyclicity:
    def test_triangle_rejected(
        self, client: TestClient, auth_token: str
    ) -> None:
        """A—B, B—C, then A—C must 409 under undirected cycle check."""
        from uuid import uuid4

        ws = _create_workspace(client, auth_token, slug="ws-undirected-cycle")
        # Owner membership from workspace create
        m_owner = client.get(
            f"/api/v1/messaging/memberships?workspace_id={ws['id']}&kind=user",
            headers=_h(auth_token),
        ).json()["items"][0]["id"]

        entity_b = _create_entity(client, auth_token, slug=f"ent-b-{uuid4().hex[:6]}")
        entity_c = _create_entity(client, auth_token, slug=f"ent-c-{uuid4().hex[:6]}")
        intro_b = client.post(
            f"/api/v1/workspaces/{ws['id']}/introduce-entity",
            headers=_h(auth_token),
            json={"entity_id": entity_b["id"]},
        )
        intro_c = client.post(
            f"/api/v1/workspaces/{ws['id']}/introduce-entity",
            headers=_h(auth_token),
            json={"entity_id": entity_c["id"]},
        )
        assert intro_b.status_code == 201, intro_b.text
        assert intro_c.status_code == 201, intro_c.text

        inst_mems = client.get(
            f"/api/v1/messaging/memberships?workspace_id={ws['id']}&kind=instance",
            headers=_h(auth_token),
        ).json()["items"]
        assert len(inst_mems) == 2
        m_b, m_c = inst_mems[0]["id"], inst_mems[1]["id"]

        for a, b in ((m_owner, m_b), (m_b, m_c)):
            resp = client.post(
                "/api/v1/messaging/passages",
                headers=_h(auth_token),
                json={
                    "workspace_id": ws["id"],
                    "from_membership_id": a,
                    "to_membership_id": b,
                },
            )
            assert resp.status_code == 201, resp.text

        closing = client.post(
            "/api/v1/messaging/passages",
            headers=_h(auth_token),
            json={
                "workspace_id": ws["id"],
                "from_membership_id": m_c,
                "to_membership_id": m_owner,
            },
        )
        assert closing.status_code == 409, closing.text
        assert closing.json()["error_code"] == "passage.would_create_cycle"
