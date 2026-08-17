"""loguru configuration: intercept stdlib logging, bind request_id, and wire sinks.

This module is called once at startup (lifespan) and is never re-imported at runtime.
"""

import logging
import sys

from loguru import logger

from app.core.config import settings


class InterceptHandler(logging.Handler):
    """Route stdlib log records through loguru so they share the same sinks and context."""

    def emit(self, record: logging.LogRecord) -> None:
        # Find the originating loguru level by walking the name hierarchy.
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find the bottom-most frame that is not in this module.
        frame = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == __file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _neutralize_uvicorn_handlers() -> None:
    """Clear uvicorn/uvicorn.access built-in handlers and enable propagation.

    Default behaviour: uvicorn attaches its own StreamHandler to `uvicorn.access`
    (with ``propagate=False``).  If we only remove the handler, the logger stays
    silent.  We must also set ``propagate=True`` so records reach the root
    logger (which InterceptHandler already proxies into loguru).
    """
    for name in ("uvicorn", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True


def configure_logging() -> None:
    """Replace the stdlib root handler with loguru and attach sinks.

    This must be called exactly once, in lifespan startup, before any request
    is handled.  It is idempotent for the root handler but changing sinks
    mid-process is intentionally unsupported.
    """
    # 1. Strip all existing loguru sinks (defaults + any previous call).
    logger.remove()

    # 2. Default extra so that {extra[request_id]} never raises KeyError in
    #    request-less contexts (lifespan, background workers, etc.).
    logger.configure(extra={"request_id": "-"})

    # 3. Attach the appropriate sink.
    if settings.ENV == "dev":
        logger.add(
            sys.stderr,
            level=settings.LOG_LEVEL,
            colorize=True,
            format=(
                "<green>{time:HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{extra[request_id]}</cyan> | "
                "<level>{message}</level>"
            ),
        )
    else:
        logger.add(
            sys.stdout,
            level=settings.LOG_LEVEL,
            serialize=True,
        )

    # 4. Bridge stdlib → loguru.
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(InterceptHandler())
    root.setLevel(settings.LOG_LEVEL)

    # 5. Neutralize uvicorn's own handlers so every log line goes through
    #    loguru exactly once.
    _neutralize_uvicorn_handlers()

    # Suppress the uvicorn.access logger to avoid duplicate request lines
    # (LoggingMiddleware already emits http.request.start / http.request.end).
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
