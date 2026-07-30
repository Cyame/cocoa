"""CentralHub + 4 brain regions + Vault (PRD-v2)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class CentralHub(BaseModel, Base):
    """1:1 collaboration hub per Workspace (主脑 container)."""

    __tablename__ = "central_hubs"
    __table_args__ = (
        Index(
            "uq_central_hubs_workspace",
            "workspace_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=False
    )
    # Free-form hub notepad (legacy surface retained for Composer / phase-6 API).
    content: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    manual_notes: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} workspace={self.workspace_id!r}>"


class FornixFile(BaseModel, Base):
    """穹窿 — virtual filesystem under CentralHub."""

    __tablename__ = "fornix_files"
    __table_args__ = (
        Index(
            "uq_fornix_files_path",
            "workspace_id",
            "parent_path",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_fornix_files_storage_key",
            "storage_key",
            unique=True,
        ),
        CheckConstraint(
            "(uploader_user_id IS NOT NULL) <> (uploader_instance_id IS NOT NULL)",
            name="ck_fornix_files_exclusive_uploader",
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=False
    )
    central_hub_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("central_hubs.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(36), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_directory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uploader_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    uploader_instance_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("instances.id"), nullable=True
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} name={self.name!r}>"


class VaultEntrySourceType(str, Enum):
    fornix_file = "fornix_file"
    workspace_file = "workspace_file"


class Vault(BaseModel, Base):
    """1:1 cold archive per Workspace."""

    __tablename__ = "vaults"
    __table_args__ = (
        Index(
            "uq_vaults_workspace",
            "workspace_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=False
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} workspace={self.workspace_id!r}>"


class VaultEntry(BaseModel, Base):
    """Archived KV entry. v2 allows inline ``value``; ``archived_key`` for future object store."""

    __tablename__ = "vault_entries"

    vault_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vaults.id"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    value: Mapped[dict | list | str | None] = mapped_column(JSONB, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} vault={self.vault_id!r}>"


class FrontalLobeKanbanStatus(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"
    blocked = "blocked"


class FrontalLobeKanban(BaseModel, Base):
    """额叶 Kanban card."""

    __tablename__ = "frontal_lobe_kanbans"
    __table_args__ = (
        Index(
            "uq_frontal_lobe_kanbans_hub_position",
            "central_hub_id",
            "position",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    central_hub_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("central_hubs.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=FrontalLobeKanbanStatus.todo.value,
    )
    assignee_entity_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("entities.id"), nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class BrainstemSchedule(BaseModel, Base):
    """脑干 scheduled task."""

    __tablename__ = "brainstem_schedules"

    central_hub_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("central_hubs.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cron_expr: Mapped[str] = mapped_column(String(100), nullable=False)
    action_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CerebellumAgent(BaseModel, Base):
    """小脑 — built-in central agent 1:1 per CentralHub. Not soft-deletable in app logic."""

    __tablename__ = "cerebellum_agents"
    __table_args__ = (
        Index(
            "uq_cerebellum_agents_hub",
            "central_hub_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    central_hub_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("central_hubs.id"), nullable=False
    )
    base_slug: Mapped[str] = mapped_column(
        String(255), nullable=False, default="cerebellum-baseclass"
    )
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    loop_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="idle"
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    installed_genes: Mapped[dict | list | None] = mapped_column(
        JSONB, nullable=True, default=list
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="cerebellum"
    )
    # Per-workspace override; null = inherit Organization cerebellum defaults
    provider_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organization_providers.id"), nullable=True
    )
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
