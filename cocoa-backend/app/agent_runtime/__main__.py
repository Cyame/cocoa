"""``python -m app.agent_runtime`` entrypoint for Instance pods."""

from __future__ import annotations

import asyncio
import os
import sys

from loguru import logger


async def _amain() -> None:
    instance_id = (os.environ.get("COCOA_INSTANCE_ID") or "").strip()
    if not instance_id:
        logger.error("COCOA_INSTANCE_ID is required in pod mode")
        raise SystemExit(2)

    # Prefer the legacy loop module (bridged via package __init__).
    from app.agent_runtime import run_agent_loop

    if run_agent_loop is None:
        logger.error("run_agent_loop unavailable")
        raise SystemExit(3)

    logger.info("starting agent runtime loop instance_id={}", instance_id)
    await run_agent_loop(instance_id)


def main() -> None:
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
