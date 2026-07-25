"""Base model mixin providing id, timestamps, and soft-delete for all models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column


class BaseModel:
    """Mixin for all domain models.

    Provides:
    - ``id``: VARCHAR(36) UUID primary key
    - ``created_at`` / ``updated_at``: auto-managed timestamps
    - ``deleted_at``: nullable timestamp for soft-delete
    - ``soft_delete()``: marks the record as deleted
    """

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    def soft_delete(self) -> None:
        """Mark this record as deleted by setting ``deleted_at`` to now."""
        self.deleted_at = datetime.now(timezone.utc)


# Base 实际定义在 app.core.db（与 engine + session factory 同处，便于集中管理连接配置）。
# 此处重导出仅为符合 P2 计划 todo 1 的字面契约，让"from app.models.base import Base"模式可用。
# 新代码请直接 `from app.core.db import Base`。
from app.core.db import Base  # noqa: E402, F401
