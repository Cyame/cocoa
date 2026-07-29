"""P11c Todo 3-5: Instance endpoint wiring tests for DeployService + K8sClient.

Three endpoint tests cover the wiring changes in
:mod:`app.api.v1.instances` introduced by P11c:

1. ``test_deploy_calls_deploy_service`` — with K8s available,
   ``POST /instances/{id}/deploy`` calls ``DeployService.deploy_instance``
   (mocked), kicks off the async pipeline (also mocked), and returns a
   :class:`DeployRecordOut` body with the expected fields.

2. ``test_deploy_local_mode_falls_back_to_db_transition`` — with
   ``COCOA_K8S_DISABLED=true`` (local dev), the deploy endpoint
   short-circuits to the P7 in-process DB transition
   (``creating``/``restarting`` → ``deploying``) instead of returning
   503.

3. ``test_delete_calls_k8s_delete_namespace`` — ``DELETE /instances/{id}``
   performs a best-effort K8s ``delete_namespace`` on the
   ``cocoa-default-{workspace_path}`` namespace, with mocked clients.

The test app is a minimal FastAPI instance that mounts only the
``auth`` and ``instances`` routers, sharing the per-test cloned
database (same ``db_url`` the ``session`` fixture provides). This
isolation lets the tests run without dragging in the rest of the
API surface from ``app.main``.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import router as auth_router
from app.api.v1.instances import router as instances_router
from app.models.workspace import Membership, MembershipRole


@pytest_asyncio.fixture
async def instances_app(db_url: str):
    """Build a minimal FastAPI app wiring the instances + auth routers.

    Mirrors the pattern from ``test_phase11c_deploy_endpoint.py``:
    wire ``app.api.deps.get_db`` to the per-test cloned database and
    mount only the routers under test.
    """
    import app.core.config as cfg_mod
    import app.core.db as db_mod

    db_mod._engine = None
    db_mod._session_factory = None

    monkey = pytest.MonkeyPatch()
    monkey.setattr(cfg_mod.settings, "DATABASE_URL", db_url)

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(instances_router, prefix="/api/v1")
    yield app
    monkey.undo()
    db_mod._engine = None
    db_mod._session_factory = None


async def _register_and_login(ac: AsyncClient, username: str) -> str:
    """Register + login via AsyncClient and return the JWT access token."""
    await ac.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@test.com",
            "password": "password123",
        },
    )
    resp = await ac.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "password123"},
    )
    return resp.json()["access_token"]


async def _link_user_to_workspace(
    session: AsyncSession, user_id: str, workspace_id: str
) -> None:
    """Insert an editor-role Membership so ``require_workspace_role`` passes.

    The Membership's ``posx`` / ``posy`` are set to (0, 0) — only the
    role matters for the endpoint under test.
    """
    session.add(
        Membership(
            user_id=user_id,
            workspace_id=workspace_id,
            posx=0,
            posy=0,
            role=MembershipRole.editor.value,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_deploy_calls_deploy_service(
    instances_app: FastAPI,
    session: AsyncSession,
    instance_factory,
    db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deploy endpoint calls DeployService.deploy_instance when K8s is available.

    Sets ``KUBECONFIG`` so :func:`_is_k8s_available` returns ``True``,
    then patches the ``svc_deploy_instance`` and
    ``svc_execute_deploy_pipeline`` references in the instances module
    with stubs that return a fake record id and a no-op pipeline. The
    endpoint should respond 200 with a ``DeployRecordOut`` body whose
    fields mirror the fake record id and ``latest`` image version.
    """
    import app.api.v1.instances as instances_mod
    import app.core.db as db_mod

    db_mod._engine = None
    db_mod._session_factory = None

    monkeypatch.delenv("COCOA_K8S_DISABLED", raising=False)
    monkeypatch.setenv("KUBECONFIG", "/tmp/cocoa-fake-kubeconfig.yaml")

    fake_record_id = "rec-" + uuid.uuid4().hex[:12]
    fake_ctx = SimpleNamespace(image_version="latest", revision=1)

    async def fake_deploy(*args, **kwargs):
        return fake_record_id, fake_ctx

    async def fake_execute(ctx):
        return None

    monkeypatch.setattr(instances_mod, "svc_deploy_instance", fake_deploy)
    monkeypatch.setattr(instances_mod, "svc_execute_deploy_pipeline", fake_execute)

    instance = await instance_factory(workspace_path="deploy-svc-1")

    transport = ASGITransport(app=instances_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        username = f"deploy_{uuid.uuid4().hex[:8]}"
        token = await _register_and_login(ac, username)
        # Decode the JWT to learn the user_id without adding a /me endpoint call.
        from jose import jwt


        user_id = jwt.get_unverified_claims(token)["sub"]
        await _link_user_to_workspace(session, user_id, instance.workspace_id)

        resp = await ac.post(
            f"/api/v1/instances/{instance.id}/deploy",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == fake_record_id
    assert body["instance_id"] == instance.id
    assert body["action"] == "deploy"
    assert body["status"] == "running"
    assert body["image_version"] == "latest"
    assert body["revision"] == 1


@pytest.mark.asyncio
async def test_deploy_local_mode_falls_back_to_db_transition(
    instances_app: FastAPI,
    session: AsyncSession,
    instance_factory,
    db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local mode (COCOA_K8S_DISABLED=true) falls back to P7 DB transition.

    With no kubeconfig / service-account / GATEWAY_KUBECONFIG and
    ``COCOA_K8S_DISABLED=true`` set, ``_is_k8s_available()`` returns
    ``False``. The deploy endpoint then short-circuits to the P7
    in-process DB transition (``creating``/``restarting`` → ``deploying``),
    keeping the legacy P7 contract usable in local dev without a
    cluster. The fallback path returns 200 with the same
    ``InstanceOut`` body the P7 contract defines.
    """
    import app.core.db as db_mod

    db_mod._engine = None
    db_mod._session_factory = None

    monkeypatch.setenv("COCOA_K8S_DISABLED", "true")
    monkeypatch.delenv("KUBECONFIG", raising=False)
    monkeypatch.delenv("GATEWAY_KUBECONFIG", raising=False)

    instance = await instance_factory(workspace_path="deploy-local-fallback")

    transport = ASGITransport(app=instances_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        username = f"local_{uuid.uuid4().hex[:8]}"
        token = await _register_and_login(ac, username)

        from jose import jwt

        user_id = jwt.get_unverified_claims(token)["sub"]
        await _link_user_to_workspace(session, user_id, instance.workspace_id)

        resp = await ac.post(
            f"/api/v1/instances/{instance.id}/deploy",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "deploying"
    assert body["id"] == instance.id
    assert body["workspace_path"] == "deploy-local-fallback"


@pytest.mark.asyncio
async def test_delete_calls_k8s_delete_namespace(
    instances_app: FastAPI,
    session: AsyncSession,
    instance_factory,
    db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DELETE /instances/{id} invokes K8s delete_namespace on the right ns.

    Mocks ``k8s_manager.get_gateway_client`` to return a fake
    ApiClient, and patches ``K8sClient`` so the resulting
    ``client.core.delete_namespace`` is a MagicMock. The test verifies
    the namespace name follows the ``cocoa-default-{workspace_path}``
    convention and that the API call returns 204.
    """
    import app.api.v1.instances as instances_mod
    import app.core.db as db_mod

    db_mod._engine = None
    db_mod._session_factory = None

    fake_api_client = MagicMock(name="ApiClient")

    async def fake_get_gateway_client():
        return fake_api_client

    monkeypatch.setattr(
        instances_mod.k8s_manager,
        "get_gateway_client",
        fake_get_gateway_client,
    )

    fake_k8s_client = MagicMock(name="K8sClient")
    fake_k8s_client.core = MagicMock()
    fake_k8s_client.core.delete_namespace = AsyncMock(return_value=None)
    monkeypatch.setattr(instances_mod, "K8sClient", MagicMock(return_value=fake_k8s_client))

    instance = await instance_factory(workspace_path="delete-ns-test")

    transport = ASGITransport(app=instances_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        username = f"delete_{uuid.uuid4().hex[:8]}"
        token = await _register_and_login(ac, username)

        from jose import jwt

        user_id = jwt.get_unverified_claims(token)["sub"]
        await _link_user_to_workspace(session, user_id, instance.workspace_id)

        resp = await ac.delete(
            f"/api/v1/instances/{instance.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 204, resp.text
    fake_k8s_client.core.delete_namespace.assert_awaited_once()
    call_args = fake_k8s_client.core.delete_namespace.call_args
    assert call_args.args[0] == f"cocoa-default-{instance.workspace_path}"
