"""Persist / load Composer transcript messages."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.composer_message import ComposerMessage
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)


async def append_composer_message(
    session: AsyncSession,
    *,
    workspace_id: str,
    role: str,
    content: str,
    target_entity: str | None = None,
    instance_id: str | None = None,
    turn_id: str | None = None,
    status: str = "completed",
    author_user_id: str | None = None,
) -> ComposerMessage | None:
    """Insert one transcript row. Resolves namespace_id from workspace."""
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        logger.warning("append_composer_message: workspace missing %s", workspace_id)
        return None
    row = ComposerMessage(
        namespace_id=workspace.namespace_id,
        workspace_id=workspace_id,
        role=role,
        content=content or "",
        target_entity=target_entity,
        instance_id=instance_id,
        turn_id=turn_id,
        status=status,
        author_user_id=author_user_id,
    )
    session.add(row)
    await session.flush()
    return row


async def update_composer_message_by_turn(
    session: AsyncSession,
    *,
    turn_id: str,
    role: str = "assistant",
    content: str | None = None,
    status: str | None = None,
) -> ComposerMessage | None:
    row = (
        await session.execute(
            select(ComposerMessage).where(
                ComposerMessage.turn_id == turn_id,
                ComposerMessage.role == role,
                ComposerMessage.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    if content is not None:
        row.content = content
    if status is not None:
        row.status = status
    await session.flush()
    return row


async def list_composer_messages(
    session: AsyncSession,
    workspace_id: str,
    *,
    limit: int = 200,
) -> list[ComposerMessage]:
    rows = (
        await session.execute(
            select(ComposerMessage)
            .where(
                ComposerMessage.workspace_id == workspace_id,
                ComposerMessage.deleted_at.is_(None),
            )
            .order_by(ComposerMessage.created_at.asc())
            .limit(min(limit, 500))
        )
    ).scalars().all()
    return list(rows)
