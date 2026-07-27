"""Unit tests for ``app.services.k8s.k8s_client.K8sClient`` (P11a).

All kubernetes_asyncio APIs are mocked — these tests never touch a
real cluster. The three tests cover the must-have surfaces called out
in P11a Todo 4:

* constructor wires up the five sub-clients
* ``ensure_namespace`` creates a missing namespace
* ``create_or_skip`` swallows 409 Conflict
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kubernetes_asyncio import client as k8s_client

from app.services.k8s.k8s_client import K8sClient
from app.services.k8s.k8s_client_watch import K8sClientWatchMixin

# ── 1. Constructor wires up the five sub-clients ────────


def test_k8s_client_init_creates_sub_clients() -> None:
    """``K8sClient(api_client)`` instantiates all 5 sub-clients."""
    api_client = MagicMock(spec=k8s_client.ApiClient)
    fake_core = MagicMock(name="CoreV1Api")
    fake_apps = MagicMock(name="AppsV1Api")
    fake_networking = MagicMock(name="NetworkingV1Api")
    fake_version = MagicMock(name="VersionApi")
    fake_custom = MagicMock(name="CustomObjectsApi")

    with patch.object(k8s_client, "CoreV1Api", return_value=fake_core) as core_cls, \
         patch.object(k8s_client, "AppsV1Api", return_value=fake_apps) as apps_cls, \
         patch.object(k8s_client, "NetworkingV1Api", return_value=fake_networking) as net_cls, \
         patch.object(k8s_client, "VersionApi", return_value=fake_version) as ver_cls, \
         patch.object(k8s_client, "CustomObjectsApi", return_value=fake_custom) as custom_cls:
        client = K8sClient(api_client)

    # constructor called each sub-client class exactly once with the api_client
    core_cls.assert_called_once_with(api_client)
    apps_cls.assert_called_once_with(api_client)
    net_cls.assert_called_once_with(api_client)
    ver_cls.assert_called_once_with(api_client)
    custom_cls.assert_called_once_with(api_client)

    # instance attributes are the objects the factories returned
    assert client.core is fake_core
    assert client.apps is fake_apps
    assert client.networking is fake_networking
    assert client.version_api is fake_version
    assert client.custom is fake_custom

    # the watch mixin is reachable (proves K8sClient inherits K8sClientWatchMixin)
    assert isinstance(client, K8sClientWatchMixin)
    assert hasattr(client, "watch_pods")
    assert hasattr(client, "stream_pod_logs")


# ── 2. ensure_namespace creates a missing namespace ─────


@pytest.mark.asyncio
async def test_ensure_namespace_creates_if_missing() -> None:
    """404 on read_namespace triggers create_namespace; existing ns is left alone."""
    api_client = MagicMock(spec=k8s_client.ApiClient)
    client = K8sClient(api_client)

    # first call (read) raises 404; second call (create) records the call
    client.core.read_namespace = AsyncMock(
        side_effect=k8s_client.ApiException(status=404, reason="Not Found")
    )
    client.core.create_namespace = AsyncMock(return_value=MagicMock(name="V1Namespace"))

    await client.ensure_namespace("cocoa-test", extra_labels={"env": "test"})

    # read was attempted once; create_namespace was called once
    client.core.read_namespace.assert_awaited_once_with("cocoa-test")
    client.core.create_namespace.assert_awaited_once()

    # the body we built carried the cocoa-managed label + the extra label
    body = client.core.create_namespace.await_args.args[0]
    labels = body.metadata.labels
    assert labels["app.kubernetes.io/managed-by"] == "cocoa"
    assert labels["env"] == "test"


# ── 3. create_or_skip swallows 409 Conflict ─────────────


@pytest.mark.asyncio
async def test_create_or_skip_handles_409() -> None:
    """A 409 from the create_fn is swallowed; other errors re-raise."""
    api_client = MagicMock(spec=k8s_client.ApiClient)
    client = K8sClient(api_client)

    # 409 path — must not raise
    already_exists = AsyncMock(
        side_effect=k8s_client.ApiException(status=409, reason="Already Exists")
    )
    result = await client.create_or_skip(already_exists, "ns", {"foo": "bar"})
    assert result is None
    already_exists.assert_awaited_once_with("ns", {"foo": "bar"})

    # non-409 path — must re-raise unchanged
    forbidden = AsyncMock(
        side_effect=k8s_client.ApiException(status=403, reason="Forbidden")
    )
    with pytest.raises(k8s_client.ApiException) as excinfo:
        await client.create_or_skip(forbidden, "ns", {"foo": "bar"})
    assert excinfo.value.status == 403
    forbidden.assert_awaited_once_with("ns", {"foo": "bar"})
