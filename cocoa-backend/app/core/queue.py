"""In-memory task queue with delayed execution.

P5/P7 will replace this with a Redis-backed implementation that shares the same
TaskQueue protocol signature — callers require zero changes. The in-memory
implementation is intentionally ephemeral: all queued tasks are lost on process
restart. The Redis implementation will address persistence.

Architecture:
- PriorityQueue ordered by (run_at, seq) — earliest run_at wins; seq breaks ties
  for tasks scheduled at the same instant, guaranteeing FIFO fairness.
- A single worker coroutine consumes the queue. It sleeps until the head task's
  run_at, using asyncio.wait_for + asyncio.Event to handle the head-of-queue
  sleep race: when enqueue() inserts a task that lands at the head, it wakes the
  worker so the worker re-evaluates the new head instead of sleeping through it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol
from uuid import uuid4

from loguru import logger

Handler = Callable[[dict], Awaitable[None]]


class TaskQueue(Protocol):
    """Protocol for task queue implementations.

    A TaskQueue accepts delayed tasks, dispatches them to registered handlers
    when their run_at arrives, and supports start/stop lifecycle.
    """

    async def enqueue(self, task_name: str, *, delay: float = 0.0, payload: dict | None = None) -> str:
        """Schedule a task for execution after `delay` seconds.

        Returns the task's unique id (a UUID string).
        """

    def register_task(self, task_name: str, handler: Handler) -> None:
        """Register a handler for a task name.

        Raises ValueError if the name is already registered.
        """

    async def start(self) -> None:
        """Start the worker coroutine (must be called from an async context)."""

    async def stop(self) -> None:
        """Gracefully stop the worker and drain the current task."""


class InMemoryTaskQueue:
    """In-memory PriorityQueue-backed task queue.

    Tasks are tuples of (run_at: float, seq: int, task_id: str, task_name: str,
    payload: dict). seq is a monotonically increasing counter that ensures
    fair scheduling when multiple tasks share the same run_at.

    The worker uses asyncio.wait_for + asyncio.Event to handle the
    head-of-queue sleep race: when a new task lands at the head of the queue
    the worker is woken up so it re-evaluates the head instead of sleeping
    through the old head's deadline.
    """

    def __init__(self) -> None:
        self._queue: asyncio.PriorityQueue[tuple[float, int, str, str, dict]] = asyncio.PriorityQueue()
        self._handlers: dict[str, Handler] = {}
        self._seq: int = 0
        self._wakeup: asyncio.Event = asyncio.Event()
        self._stopping: bool = False
        self._worker_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def enqueue(self, task_name: str, *, delay: float = 0.0, payload: dict | None = None) -> str:
        """Schedule a task. Returns the task_id."""
        if task_name not in self._handlers:
            raise ValueError(f"Unknown task name: {task_name}")
        loop = asyncio.get_running_loop()
        task_id = str(uuid4())
        run_at = loop.time() + delay
        self._seq += 1
        await self._queue.put((run_at, self._seq, task_id, task_name, payload or {}))
        self._wakeup.set()
        logger.debug("Task enqueued", task_name=task_name, task_id=task_id, delay=delay)
        return task_id

    def register_task(self, task_name: str, handler: Handler) -> None:
        """Register a handler for a task name."""
        if task_name in self._handlers:
            raise ValueError(f"Task {task_name} already registered")
        self._handlers[task_name] = handler

    async def start(self) -> None:
        """Start the worker coroutine."""
        if self._worker_task is not None:
            return
        self._stopping = False
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("TaskQueue worker started")

    async def stop(self) -> None:
        """Stop the worker and drain the current task."""
        self._stopping = True
        self._wakeup.set()
        if self._worker_task is not None:
            await self._worker_task
            self._worker_task = None
        logger.info("TaskQueue worker stopped")

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    async def _worker_loop(self) -> None:
        """Main worker coroutine: pop head, sleep until run_at, dispatch."""
        while not self._stopping:
            if self._queue.empty():
                self._wakeup.clear()
                await self._wakeup.wait()
                continue

            run_at, seq, task_id, task_name, payload = self._queue.get_nowait()
            loop = asyncio.get_running_loop()
            delay = run_at - loop.time()

            if delay <= 0:
                # Already due — execute immediately.
                await self._execute(task_name, task_id, payload)
                self._queue.task_done()
                continue

            # Sleep until the head task is due, but stay responsive to new
            # enqueues that may land ahead of the current head.
            self._wakeup.clear()
            try:
                await asyncio.wait_for(self._wakeup.wait(), timeout=delay)
            except TimeoutError:
                # Deadline reached — execute the head task.
                await self._execute(task_name, task_id, payload)
                self._queue.task_done()
            else:
                # Woken up by a new enqueue. Re-insert the current head
                # (run_at and seq unchanged) so the worker re-evaluates
                # the (possibly new) head on the next loop iteration.
                await self._queue.put((run_at, seq, task_id, task_name, payload))
                # _wakeup is already cleared; the next iteration will
                # either pop the new head or wait again.

    async def _execute(self, task_name: str, task_id: str, payload: dict) -> None:
        """Dispatch a task to its registered handler.

        Handler exceptions are caught and logged — the worker MUST NOT crash
        so that subsequent tasks continue to be processed.
        """
        handler = self._handlers.get(task_name)
        if handler is None:
            logger.warning("No handler for task", task_name=task_name, task_id=task_id)
            return
        try:
            logger.debug("Executing task", task_name=task_name, task_id=task_id)
            await handler(payload)
        except Exception:
            logger.exception("Task handler failed", task_name=task_name, task_id=task_id)
