"""Persist / load Composer transcript messages."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.composer_message import ComposerMessage
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)


def _user_display_label(*, nickname: str | None, username: str) -> str:
    """Prefer nickname (大名), then username (slug-like)."""
    if nickname and nickname.strip():
        return nickname.strip()
    return username


def _entity_display_label(*, display_name: str | None, name: str | None, slug: str) -> str:
    """Prefer 大名 (display_name), then name, then slug."""
    for candidate in (display_name, name, slug):
        if candidate and str(candidate).strip():
            return str(candidate).strip()
    return slug


def _parse_party(value: str | None) -> tuple[str, str] | None:
    """Parse ``user:name`` / ``entity:slug`` / ``system`` filter tokens."""
    if not value:
        return None
    if value == "system":
        return ("system", "")
    if ":" not in value:
        return None
    kind, _, rest = value.partition(":")
    rest = rest.strip()
    if kind not in ("user", "entity") or not rest:
        return None
    return (kind, rest)


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
    instance_id: str | None = None,
    role: str | None = None,
    target_entity: str | None = None,
    author_username: str | None = None,
    speaker: str | None = None,
    recipient: str | None = None,
) -> list[ComposerMessage]:
    from app.models.user import User

    clauses = [
        ComposerMessage.workspace_id == workspace_id,
        ComposerMessage.deleted_at.is_(None),
    ]
    if instance_id:
        clauses.append(ComposerMessage.instance_id == instance_id)

    speaker_party = _parse_party(speaker)
    recipient_party = _parse_party(recipient)

    # Legacy role / author / target filters (still used by tests + instance scope).
    if role and not speaker_party:
        clauses.append(ComposerMessage.role == role)
    if target_entity and not speaker_party and not recipient_party:
        clauses.append(ComposerMessage.target_entity == target_entity)
    if author_username and not speaker_party:
        user_ids = (
            await session.execute(
                select(User.id).where(
                    User.username == author_username,
                    User.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        if not user_ids:
            return []
        clauses.append(ComposerMessage.author_user_id.in_(list(user_ids)))

    if speaker_party:
        kind, value = speaker_party
        if kind == "system":
            clauses.append(ComposerMessage.role == "system")
        elif kind == "user":
            user_ids = (
                await session.execute(
                    select(User.id).where(
                        User.username == value,
                        User.deleted_at.is_(None),
                    )
                )
            ).scalars().all()
            if not user_ids:
                return []
            clauses.append(ComposerMessage.role == "user")
            clauses.append(ComposerMessage.author_user_id.in_(list(user_ids)))
        elif kind == "entity":
            # Lost One speaking: assistant rows keyed by target_entity slug.
            clauses.append(ComposerMessage.role == "assistant")
            clauses.append(ComposerMessage.target_entity == value)

    if recipient_party:
        kind, value = recipient_party
        if kind == "entity":
            # Human → Lost One: user rows addressed to that entity.
            clauses.append(ComposerMessage.role == "user")
            clauses.append(ComposerMessage.target_entity == value)
        elif kind == "user":
            # Lost One → human: assistant rows whose turn's user author matches.
            user_ids = (
                await session.execute(
                    select(User.id).where(
                        User.username == value,
                        User.deleted_at.is_(None),
                    )
                )
            ).scalars().all()
            if not user_ids:
                return []
            turn_ids = (
                await session.execute(
                    select(ComposerMessage.turn_id).where(
                        ComposerMessage.workspace_id == workspace_id,
                        ComposerMessage.role == "user",
                        ComposerMessage.author_user_id.in_(list(user_ids)),
                        ComposerMessage.turn_id.is_not(None),
                        ComposerMessage.deleted_at.is_(None),
                    )
                )
            ).scalars().all()
            if not turn_ids:
                return []
            clauses.append(ComposerMessage.role == "assistant")
            clauses.append(ComposerMessage.turn_id.in_(list(turn_ids)))

    rows = (
        await session.execute(
            select(ComposerMessage)
            .where(*clauses)
            .order_by(ComposerMessage.created_at.asc())
            .limit(min(limit, 500))
        )
    ).scalars().all()
    return list(rows)


async def enrich_composer_message_items(
    session: AsyncSession,
    rows: list[ComposerMessage],
) -> list[dict]:
    """Serialize transcript rows with speaker / recipient display labels."""
    from app.models.entity import Entity
    from app.models.user import User

    user_ids = [r.author_user_id for r in rows if r.author_user_id]
    user_map: dict[str, tuple[str, str | None]] = {}
    if user_ids:
        users = (
            await session.execute(
                select(User).where(User.id.in_(user_ids), User.deleted_at.is_(None))
            )
        ).scalars().all()
        user_map = {u.id: (u.username, u.nickname) for u in users}

    # Resolve recipient for assistant rows via same-turn user message.
    turn_ids = [r.turn_id for r in rows if r.role == "assistant" and r.turn_id]
    turn_author: dict[str, tuple[str, str | None]] = {}
    if turn_ids:
        user_rows = (
            await session.execute(
                select(ComposerMessage).where(
                    ComposerMessage.turn_id.in_(turn_ids),
                    ComposerMessage.role == "user",
                    ComposerMessage.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        missing_uids = [
            ur.author_user_id
            for ur in user_rows
            if ur.author_user_id and ur.author_user_id not in user_map
        ]
        if missing_uids:
            extra = (
                await session.execute(
                    select(User).where(
                        User.id.in_(missing_uids), User.deleted_at.is_(None)
                    )
                )
            ).scalars().all()
            for u in extra:
                user_map[u.id] = (u.username, u.nickname)
        for ur in user_rows:
            if ur.turn_id and ur.author_user_id and ur.author_user_id in user_map:
                turn_author[ur.turn_id] = user_map[ur.author_user_id]

    slugs = sorted({r.target_entity for r in rows if r.target_entity})
    entity_label: dict[str, str] = {}
    if slugs and rows:
        workspace = await session.get(Workspace, rows[0].workspace_id)
        if workspace is not None:
            entities = (
                await session.execute(
                    select(Entity).where(
                        Entity.namespace_id == workspace.namespace_id,
                        Entity.slug.in_(slugs),
                        Entity.deleted_at.is_(None),
                    )
                )
            ).scalars().all()
            for ent in entities:
                entity_label[ent.slug] = _entity_display_label(
                    display_name=ent.display_name,
                    name=ent.name,
                    slug=ent.slug,
                )

    items: list[dict] = []
    for row in rows:
        author_username = None
        author_nickname = None
        author_display = None
        if row.author_user_id and row.author_user_id in user_map:
            author_username, author_nickname = user_map[row.author_user_id]
            author_display = _user_display_label(
                nickname=author_nickname, username=author_username
            )
        target_name = (
            entity_label.get(row.target_entity, row.target_entity)
            if row.target_entity
            else None
        )
        recipient_username = None
        recipient_nickname = None
        recipient_display = None
        if row.role == "assistant" and row.turn_id and row.turn_id in turn_author:
            recipient_username, recipient_nickname = turn_author[row.turn_id]
            recipient_display = _user_display_label(
                nickname=recipient_nickname, username=recipient_username
            )
        items.append(
            {
                "id": row.id,
                "role": row.role,
                "content": row.content,
                "target_entity": row.target_entity,
                "target_entity_name": target_name,
                "instance_id": row.instance_id,
                "turn_id": row.turn_id,
                "status": row.status,
                "author_user_id": row.author_user_id,
                "author_username": author_username,
                "author_nickname": author_nickname,
                "author_display_name": author_display,
                "recipient_username": recipient_username,
                "recipient_nickname": recipient_nickname,
                "recipient_display_name": recipient_display,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return items
