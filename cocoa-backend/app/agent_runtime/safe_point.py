"""Safe-point guard for soft-inject / wake delivery (v4.7 H6).

Acceptance constraint: a soft-inject (or wake) payload MUST NOT be
spliced between a provider ``tool_use`` block and its ``tool_result``
responses — doing so breaks provider tool pairing. The guard holds every
delivery and releases it only at a *safe point*: the moment the current
tool-result batch is complete, before the next provider call.

The current agent runtime is a stub / event-driven loop with no real
provider tool lifecycle, so the runtime tracks the batch lifecycle
explicitly via :meth:`SafePointGuard.on_tool_use` /
:meth:`SafePointGuard.on_tool_results`. The guard is deterministic and
unit-testable today and slots into a real provider loop later unchanged.
"""

from __future__ import annotations

from typing import Any


class SafePointGuard:
    """Hold inject items until the next safe point (post tool-results).

    - ``hold(item)`` — queue a soft_inject / wake delivery.
    - ``on_tool_use()`` — provider emitted a ``tool_use``; tool results
      are now outstanding, so the guard leaves the safe-point zone.
    - ``on_tool_results()`` — the tool results for the batch are complete;
      the guard re-enters the safe-point zone.
    - ``flush()`` — deliver held items iff at a safe point; returns the
      delivered items and never splits a tool_use/tool_result pair.
    """

    def __init__(self) -> None:
        self._pending: list[dict[str, Any]] = []
        self._outstanding_tool_batches = 0

    @property
    def pending_count(self) -> int:
        """Number of items currently held (not yet flushed)."""
        return len(self._pending)

    @property
    def at_safe_point(self) -> bool:
        """True iff no tool-result batch is outstanding."""
        return self._outstanding_tool_batches == 0

    def hold(self, item: dict[str, Any]) -> None:
        self._pending.append(item)

    def on_tool_use(self) -> None:
        self._outstanding_tool_batches += 1

    def on_tool_results(self) -> None:
        self._outstanding_tool_batches = max(0, self._outstanding_tool_batches - 1)

    def flush(self) -> list[dict[str, Any]]:
        """Deliver held items iff at a safe point; else return ``[]``."""
        if not self.at_safe_point or not self._pending:
            return []
        delivered, self._pending = self._pending, []
        return delivered
