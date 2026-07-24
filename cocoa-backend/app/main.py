"""FastAPI application entry point for the Cocoa backend."""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle stub. Real init hooks land in P1/P2."""
    yield


app = FastAPI(
    title="Cocoa Backend",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe. Returns 200 while the process is up."""
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=4510)
