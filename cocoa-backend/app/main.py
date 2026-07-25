"""FastAPI application entry point for the Cocoa backend."""

import json
import traceback
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.db import get_session_factory
from app.core.errors import (
    CocoaError,
    ConflictError,  # noqa: F401
    ForbiddenError,  # noqa: F401
    InternalError,  # noqa: F401
    NotFoundError,
    UnauthorizedError,  # noqa: F401
    ValidationError,  # noqa: F401
    error_response,
)
from app.core.event_types import SYSTEM_SHUTDOWN, SYSTEM_STARTUP
from app.core.events import emit
from app.core.logging import configure_logging
from app.core.middleware.auth import AuthMiddleware
from app.core.middleware.logging import LoggingMiddleware
from app.core.middleware.rate_limit import RateLimitMiddleware
from app.core.middleware.request_id import RequestIDMiddleware
from app.core.queue import InMemoryTaskQueue


async def _noop_handler(payload: dict) -> None:
    """No-op handler for system.noop — smoke test for the task queue."""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    configure_logging()

    # Task queue (in-memory; P5/P7 replaces with Redis, protocol unchanged).
    queue = InMemoryTaskQueue()
    queue.register_task("system.noop", _noop_handler)
    app.state.task_queue = queue
    await queue.start()

    # Load preset registry from DB before accepting requests.
    try:
        from app.core.preset_registry import registry

        async with get_session_factory()() as s:
            await registry.load(s)
    except Exception:
        logger.opt(exception=True).error("Failed to load preset registry")

    try:
        async with get_session_factory()() as s:
            await emit(
                SYSTEM_STARTUP,
                actor_type="system",
                payload={"env": settings.ENV},
                session=s,
            )
            await s.commit()
    except Exception:
        logger.opt(exception=True).error("Failed to emit system.startup event")

    yield

    try:
        async with get_session_factory()() as s:
            await emit(
                SYSTEM_SHUTDOWN,
                actor_type="system",
                session=s,
            )
            await s.commit()
    except Exception:
        logger.opt(exception=True).error("Failed to emit system.shutdown event")

    await queue.stop()


app = FastAPI(
    title="Cocoa API",
    description="Multi-agent control studio API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    swagger_ui_parameters={"defaultModelsExpandDepth": -1},
    openapi_tags=[
        {"name": "Health", "description": "Liveness and readiness probes"},
        {"name": "Auth", "description": "Authentication and registration"},
        {"name": "EmployeePresets", "description": "Agent preset template management"},
        {"name": "Employees", "description": "Employee and agent cell management"},
        {"name": "Offices", "description": "Office workspace management"},
        {"name": "Instances", "description": "Instance lifecycle"},
        {"name": "Messaging", "description": "Agent messaging"},
        {"name": "Blackboard", "description": "Shared collaboration surface"},
        {"name": "Learning", "description": "Persistent learning and /distill"},
    ],
)


@app.exception_handler(CocoaError)
async def cocoa_error_handler(request: Request, exc: CocoaError) -> JSONResponse:
    """Serialize CocoaError subclasses into the standard error envelope."""
    response = error_response(exc)
    content = json.loads(response.body)
    content["request_id"] = getattr(request.state, "request_id", None)
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Convert native 404/405/etc into the standard error envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "error_code": f"http.{exc.status_code}",
            "message_key": f"errors.http.{exc.status_code}",
            "message": exc.detail,
            "details": None,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Convert request-schema validation failures into the standard envelope."""
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "validation_error",
            "message_key": "errors.validation",
            "message": "Request validation failed",
            "details": {"errors": jsonable_encoder(exc.errors())},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected failures; traceback leaks only in dev."""
    details = None
    if settings.ENV == "dev":
        details = {"traceback": traceback.format_exc()}
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "internal_error",
            "message_key": "errors.internal",
            "message": "Internal server error",
            "details": details,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


if settings.ENV == "dev":
    # Permanently retained for integration tests (Todo 8) and rate-limit QA (Todo 2).
    @app.get("/api/v1/error-test")
    async def error_test() -> None:
        """Dev-only endpoint that always raises a structured 404."""
        raise NotFoundError("test.not_found", "errors.test.not_found", "Test error endpoint")


# Registration order is REVERSED vs execution order because Starlette inserts each
# middleware at stack position 0 (`user_middleware.insert(0, ...)`), so the LAST
# add_middleware call ends up outermost and executes FIRST.
# Execution order (outer → inner): RequestID → Logging → CORS → Auth → RateLimit.
# Registration call order:          RateLimit → Auth → CORS → Logging → RequestID.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Dev default; tighten per-environment in P7.
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIDMiddleware)


app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe. Returns 200 while the process is up."""
    return {"status": "ok", "version": "1.0.0"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=4510, log_config=None)
