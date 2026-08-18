"""Tests for deterministic pytest environment setup."""

import os
from unittest.mock import patch

from tests import conftest


def test_pytest_configure_removes_external_proxy_settings(monkeypatch) -> None:
    """Mocked provider tests must not inherit a host HTTP or SOCKS proxy."""
    proxy_vars = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    )
    for name in proxy_vars:
        monkeypatch.setenv(name, "socks5://127.0.0.1:7897")

    conftest.pytest_configure(None)

    assert all(name not in os.environ for name in proxy_vars)


def test_alembic_subprocess_restores_original_proxy_settings(monkeypatch) -> None:
    """Alembic retains the original proxy without leaking it into pytest."""
    original_proxy = {
        "HTTP_PROXY": "http://proxy.example:8080",
        "https_proxy": "socks5://proxy.example:1080",
    }
    monkeypatch.setattr(conftest, "_ORIGINAL_PROXY_ENV", original_proxy)
    for name in conftest._PROXY_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    with patch.object(conftest.subprocess, "run") as run:
        conftest._run_alembic_upgrade("eyot_test_template")

    env = run.call_args.kwargs["env"]
    assert env["HTTP_PROXY"] == original_proxy["HTTP_PROXY"]
    assert env["https_proxy"] == original_proxy["https_proxy"]
    assert all(name not in os.environ for name in conftest._PROXY_ENV_VARS)
