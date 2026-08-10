"""v5.1 subagent_strategy: overlay 透传 + 白名单校验（真实 API 路径）。

* ``_manifest_template_subset``：manifest 有 ``subagent_strategy`` 原样流出，
  无则 ``{}``（供 prompt scaffold 提示，v5-1-definition.md :62）。
* ``validate_subagent_strategy``：enabled ⊆ 6 能力目录白名单，未知 id /
  非 list 抛 ``ValueError``；无 subagent_strategy 时 no-op。
* ``BaseClassCreate`` / ``BaseClassUpdate``：manifest 是裸 dict，PresetManifest
  的 field validator 在 API 路径是死代码（v5-1-definition.md :64）——白名单
  校验挂在 create/update schema 的 model_validator 上（schemas/base_class.py），
  本文件直接实例化 schema 并打 HTTP 端点验证真实路径已接线。
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

from app.core.overlay import _manifest_template_subset
from app.schemas.base_class import BaseClassCreate, BaseClassUpdate
from app.schemas.preset import SUBAGENT_ABILITY_IDS, validate_subagent_strategy

VALID_STRATEGY = {
    "enabled": ["intent", "architecture", "quality"],
    "constraints": {"max_parallel": 4},
}


def _auth(token: str) -> dict[str, str]:
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


def _uid() -> str:
    return uuid.uuid4().hex[:6]


# ── overlay `_manifest_template_subset` 透传 ─────────────────────────


def test_manifest_template_subset_passes_subagent_strategy_through() -> None:
    manifest = {
        "prompt": "p",
        "commands": ["plan"],
        "subagent_strategy": VALID_STRATEGY,
    }
    subset = _manifest_template_subset(manifest)
    assert subset["subagent_strategy"] == VALID_STRATEGY


def test_manifest_template_subset_defaults_to_empty_strategy() -> None:
    subset = _manifest_template_subset({"prompt": "p"})
    assert subset["subagent_strategy"] == {}


# ── `validate_subagent_strategy` 白名单单元行为 ───────────────────────


def test_validate_accepts_all_known_ability_ids() -> None:
    manifest = {"subagent_strategy": {"enabled": sorted(SUBAGENT_ABILITY_IDS)}}
    validate_subagent_strategy(manifest)  # must not raise


def test_validate_rejects_unknown_ability_id() -> None:
    manifest = {"subagent_strategy": {"enabled": ["hacker"]}}
    with pytest.raises(ValueError, match="hacker"):
        validate_subagent_strategy(manifest)


def test_validate_rejects_non_list_enabled() -> None:
    for bad in ("intent", {"intent"}, 42):
        with pytest.raises(ValueError, match="enabled"):
            validate_subagent_strategy(
                {"subagent_strategy": {"enabled": bad}}
            )


def test_validate_rejects_non_dict_strategy() -> None:
    with pytest.raises(ValueError, match="subagent_strategy"):
        validate_subagent_strategy({"subagent_strategy": ["intent"]})


def test_validate_noop_without_subagent_strategy() -> None:
    validate_subagent_strategy({"prompt": "p"})  # must not raise
    validate_subagent_strategy({"subagent_strategy": None})  # must not raise


# ── schema 层：BaseClass create/update 实际校验路径（API 请求必经）─────


def test_base_class_create_accepts_valid_strategy() -> None:
    bc = BaseClassCreate(
        slug="custom-fox",
        name="Custom Fox",
        manifest={"prompt": "p", "subagent_strategy": VALID_STRATEGY},
    )
    assert bc.manifest["subagent_strategy"] == VALID_STRATEGY


def test_base_class_create_rejects_unknown_ability_id() -> None:
    with pytest.raises(ValidationError, match="hacker"):
        BaseClassCreate(
            slug="bad-fox",
            name="Bad Fox",
            manifest={
                "prompt": "p",
                "subagent_strategy": {"enabled": ["hacker"]},
            },
        )


def test_base_class_create_rejects_non_list_enabled() -> None:
    with pytest.raises(ValidationError, match="enabled"):
        BaseClassCreate(
            slug="bad-fox-2",
            name="Bad Fox",
            manifest={
                "prompt": "p",
                "subagent_strategy": {"enabled": "intent"},
            },
        )


def test_base_class_update_accepts_valid_strategy() -> None:
    bc = BaseClassUpdate(
        manifest={"prompt": "p", "subagent_strategy": VALID_STRATEGY}
    )
    assert bc.manifest["subagent_strategy"] == VALID_STRATEGY


def test_base_class_update_rejects_unknown_ability_id() -> None:
    with pytest.raises(ValidationError, match="hacker"):
        BaseClassUpdate(
            manifest={
                "prompt": "p",
                "subagent_strategy": {"enabled": ["hacker"]},
            }
        )


# ── HTTP 端点层：白名单校验在真实 POST/PATCH 请求路径生效 ─────────────


@pytest.mark.asyncio
async def test_create_base_class_accepts_valid_subagent_strategy(
    client: TestClient, create_org_bundle
) -> None:
    token, member_id = _register(client, f"v51-a-{_uid()}", f"v51-a-{_uid()}@t.co")
    bundle = await create_org_bundle(
        member_id, atoms=("can_manage_organization",)
    )
    headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

    resp = client.post(
        "/api/v1/base-classes",
        headers=headers,
        json={
            "slug": f"v51-fox-{_uid()}",
            "name": "V5.1 Fox",
            "manifest": {"prompt": "p", "subagent_strategy": VALID_STRATEGY},
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["manifest"]["subagent_strategy"] == VALID_STRATEGY


@pytest.mark.asyncio
async def test_create_base_class_rejects_unknown_subagent_id(
    client: TestClient, create_org_bundle
) -> None:
    token, member_id = _register(client, f"v51-b-{_uid()}", f"v51-b-{_uid()}@t.co")
    bundle = await create_org_bundle(
        member_id, atoms=("can_manage_organization",)
    )
    headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

    resp = client.post(
        "/api/v1/base-classes",
        headers=headers,
        json={
            "slug": f"v51-bad-{_uid()}",
            "name": "V5.1 Bad",
            "manifest": {
                "prompt": "p",
                "subagent_strategy": {"enabled": ["hacker"]},
            },
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "validation_error"
    assert "hacker" in str(body["details"])


@pytest.mark.asyncio
async def test_update_base_class_rejects_bad_subagent_strategy(
    client: TestClient, create_org_bundle
) -> None:
    token, member_id = _register(client, f"v51-c-{_uid()}", f"v51-c-{_uid()}@t.co")
    bundle = await create_org_bundle(
        member_id, atoms=("can_manage_organization",)
    )
    headers = {**_auth(token), "X-Organization-Id": bundle.org.id}

    created = client.post(
        "/api/v1/base-classes",
        headers=headers,
        json={
            "slug": f"v51-upd-{_uid()}",
            "name": "V5.1 Update Target",
            "manifest": {"prompt": "p"},
        },
    )
    assert created.status_code == 201, created.text
    bc_id = created.json()["id"]

    ok = client.patch(
        f"/api/v1/base-classes/{bc_id}",
        headers=headers,
        json={"manifest": {"prompt": "p2", "subagent_strategy": VALID_STRATEGY}},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["manifest"]["subagent_strategy"] == VALID_STRATEGY

    bad = client.patch(
        f"/api/v1/base-classes/{bc_id}",
        headers=headers,
        json={
            "manifest": {
                "prompt": "p3",
                "subagent_strategy": {"enabled": "hacker"},
            }
        },
    )
    assert bad.status_code == 422
    assert bad.json()["error_code"] == "validation_error"
