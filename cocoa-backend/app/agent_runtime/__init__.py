"""Agent runtime — real LLM-powered Boulder loop (P14a).

Canonical home is :mod:`app.agent_runtime.loop`; the package re-exports
the two public entry points used by ``app.api.v1.harness``,
``app.core.meeting_wake`` and ``app.core.activation_consumer``.
"""

from app.agent_runtime.loop import run_agent_loop, start_runtime_for

__all__ = ["run_agent_loop", "start_runtime_for"]
