"""K8s pod mode detection + HTTP adapter for agent runtime.

P11c introduces this adapter so that ``app/agent_runtime.py`` can branch
between two modes:

- **Local mode** (``COCOA_POD_MODE != "true"``): in-process event emit +
  register HARNESS_CONTROL_SENT handler (P8 plan).

- **K8s mode** (``COCOA_POD_MODE == "true"``): HTTP POST to backend's
  ``/api/v1/internal/events/emit`` + DB polling for control events.

The adapter centralizes env-var reads so the runtime logic stays clean.
"""

from __future__ import annotations

import os

import httpx


def is_k8s_pod_mode() -> bool:
    """Return True iff the agent is running inside a K8s pod."""
    return os.environ.get("COCOA_POD_MODE", "").lower() == "true"


def get_api_url() -> str:
    """Backend HTTP base URL, e.g. ``http://cocoa-backend-svc:4510``."""
    return os.environ.get("COCOA_API_URL", "http://cocoa-backend-svc:4510")


def get_api_token() -> str:
    """Backend internal endpoint token (matches ``COCOA_API_TOKEN`` env on backend)."""
    return os.environ.get("COCOA_API_TOKEN", "")


def get_proxy_token() -> str:
    """Per-instance proxy token (matches ``Instance.proxy_token`` in DB)."""
    return os.environ.get("COCOA_PROXY_TOKEN", "")


def get_instance_id() -> str:
    """Own instance ID (matches ``Instance.id`` in DB)."""
    return os.environ.get("COCOA_INSTANCE_ID", "")


def get_httpx_client(timeout: float = 5.0) -> httpx.AsyncClient:
    """Return a configured httpx async client for backend HTTP calls."""
    return httpx.AsyncClient(timeout=timeout)


async def emit_event(
    event_type: str,
    actor_type: str,
    actor_id: str,
    resource_type: str,
    resource_id: str,
    payload: dict,
) -> str | None:
    """POST an event to the backend's internal endpoint. Returns event_id."""
    body = {
        "type": event_type,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "payload": payload,
    }
    headers = {"Authorization": f"Bearer {get_api_token()}"}
    async with get_httpx_client() as client:
        resp = await client.post(
            f"{get_api_url()}/api/v1/internal/events/emit",
            json=body,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json().get("event_id")


async def poll_control(last_seen_id: int = 0) -> list[dict]:
    """GET recent control events for this instance from backend.

    Returns only the ``events`` list (pre-v4.7 contract — signature kept
    for existing callers); v4.7 inject queue items come from
    :func:`poll_control_full`.
    """
    data = await poll_control_full(last_seen_id)
    return data.get("events", [])


async def poll_control_full(last_seen_id: int = 0) -> dict:
    """GET control events AND pending inject queue items in one call.

    Backend response shape: ``{"events": [...], "last_seen_id": int,
    "injects": [{queue_id, kind, delivery_mode, payload, tldr,
    expires_at}]}``. Polling marks the inject rows ``delivered`` on the
    backend, so a caller that crashes before acking re-polling will not
    see them again.
    """
    params = {"instance_id": get_instance_id(), "last_seen_id": last_seen_id}
    headers = {"Authorization": f"Bearer {get_api_token()}"}
    async with get_httpx_client() as client:
        resp = await client.get(
            f"{get_api_url()}/api/v1/internal/control/poll",
            params=params,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


async def ack_injects(queue_ids: list[str]) -> int:
    """Ack delivered inject queue items; returns the acked count.

    POSTs to ``/api/v1/internal/control/ack``; the backend emits
    ``harness.inject_applied`` for soft_inject / wake rows.
    """
    headers = {"Authorization": f"Bearer {get_api_token()}"}
    async with get_httpx_client() as client:
        resp = await client.post(
            f"{get_api_url()}/api/v1/internal/control/ack",
            json={"queue_ids": queue_ids},
            headers=headers,
        )
        resp.raise_for_status()
        return int(resp.json().get("acked", 0))
