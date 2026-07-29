"""CentralHub and Vault models — Office-scoped collaboration and archival storage.

> **15d-rename (2026-07-29)**: Renamed from `blackboard.py`. Class names are now
> `CentralHub` / `FornixFile` / `Vault` / `VaultEntry`. The underlying table names
> (`blackboards` / `blackboard_files` / `vaults` / `vault_entries`) are kept as
> legacy aliases in this wave — a follow-up migration in 15d-rename-2 will rename
> tables atomically.
>
> **CentralHub = 4-脑区协作中枢** (see `docs/blackboard-system.md`):
> - 穹窿 (fornix) = workspace 共通工作目录 → modeled by `FornixFile`
> - 额叶 (frontal lobe) = Kanban + todo → table added in 15d-rename-2
> - 脑干 (brainstem) = scheduled tasks → table added in 15d-rename-2
> - 小脑 (cerebellum) = central system agent → table added in 15d-rename-2
>
> v1 (P2-P8): This file shipped the **container** (`CentralHub`) and the
> **fornix virtual filesystem** (`FornixFile`).
>
> v1.5 (phase-15f): adds the remaining 3 brain region tables —
> 额叶 (`FrontalLobeKanban`) / 脑干 (`BrainstemSchedule`) /
> 小脑 (`CerebellumAgent`).
"""

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
    """1:1 shared collaboration context per Office.

    Each office has exactly one CentralHub (1:1). Hosts the 4 脑区 (穹窿 /
    额叶 / 脑干 / 小脑). v1 only persists `content` (system summary) and
    `manual_notes`; the 4-brain subtables are added in 15d-rename-2.
    """

    __tablename__ = "blackboards"  # legacy table name — rename in 15d-rename-2
    __table_args__ = (
        Index(
            "uq_blackboards_office",
            "office_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    office_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("offices.id"), nullable=False
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} office={self.office_id!r}>"


class FornixFile(BaseModel, Base):
    """穹窿 (fornix) = a file or directory within CentralHub's virtual filesystem.

    Files are keyed by storage_key (globally unique, not soft-deleted).
    Directory entries have is_directory=True.
    Uploader is either a human user or an Instance -- enforced via CHECK (XOR).

    This is the **穹窿脑区** of the CentralHub. The other 3 brain tables
    (frontal_lobe_kanbans, brainstem_schedules, cerebellum_agents) are
    added in 15d-rename-2.
    """

    __tablename__ = "blackboard_files"  # legacy — rename to fornix_files in 15d-rename-2
    __table_args__ = (
        Index(
            "uq_blackboard_files_path",
            "office_id",
            "parent_path",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_blackboard_files_storage_key",
            "storage_key",
            unique=True,
        ),
        CheckConstraint(
            "(uploader_user_id IS NOT NULL) <> (uploader_instance_id IS NOT NULL)",
            name="ck_blackboard_files_exclusive_uploader",
        ),
    )

    office_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("offices.id"), nullable=False
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
        return (
            f"<{cls} {self.id!r} name={self.name!r}"
            f" office={self.office_id!r}>"
        )


class VaultEntrySourceType(str, Enum):
    """Origin types for archiving entries into a Vault."""

    fornix_file = "fornix_file"  # 15d+ canonical (was "blackboard_file" pre-rename)
    workspace_file = "workspace_file"


class Vault(BaseModel, Base):
    """1:1 archival storage per Office.

    Each office has exactly one Vault for long-term artifact preservation.
    """

    __tablename__ = "vaults"
    __table_args__ = (
        Index(
            "uq_vaults_office",
            "office_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    office_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("offices.id"), nullable=False
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"<{cls} {self.id!r} office={self.office_id!r}>"


class VaultEntry(BaseModel, Base):
    """An archived artifact entry within a Vault.

    Tracks what was archived (source_type + source_ref), when (archived_at),
    and the storage key for retrieval.

    Inherits BaseModel timestamps normally (no updated_at override).
    """

    __tablename__ = "vault_entries"

    vault_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vaults.id"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} vault={self.vault_id!r}"
            f" source_type={self.source_type!r}>"
        )


# ---------------------------------------------------------------------------
# phase-15f: 3 remaining brain region subtables (see docs/blackboard-system.md).
# 额叶 / 脑干 / 小脑 FK to `blackboards.id` (CentralHub's table), not to offices.
# ---------------------------------------------------------------------------


class FrontalLobeKanbanStatus(str, Enum):
    """Kanban card status for the 额叶 (frontal lobe) brain region."""

    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class FrontalLobeKanban(BaseModel, Base):
    """额叶 (frontal lobe) = Kanban / todo card attached to a CentralHub.

    Lightweight task board inside the workspace's CentralHub. Position is an
    int (caller-defined — e.g. ordering within a column). Assignee is an
    optional FK to ``employees.id`` (the agent who will own the work).
    """

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
        String(36), ForeignKey("blackboards.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=FrontalLobeKanbanStatus.todo.value,
    )
    assignee_employee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} hub={self.central_hub_id!r}"
            f" status={self.status!r} title={self.title!r}>"
        )


class BrainstemSchedule(BaseModel, Base):
    """脑干 (brainstem) = scheduled task attached to a CentralHub.

    Cron-driven background action. ``action_payload`` is opaque JSON whose
    shape depends on the handler that consumes it (e.g. {type, target, body}).
    ``last_run_at`` / ``next_run_at`` are managed by the scheduler; this
    schema only stores them.
    """

    __tablename__ = "brainstem_schedules"

    central_hub_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("blackboards.id"), nullable=False
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

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} hub={self.central_hub_id!r}"
            f" cron={self.cron_expr!r} enabled={self.enabled!r}>"
        )


class CerebellumAgentType(str, Enum):
    """Agent role for the 小脑 (cerebellum) brain region."""

    orchestrator = "orchestrator"
    planner = "planner"
    executor = "executor"
    observer = "observer"


class CerebellumAgent(BaseModel, Base):
    """小脑 (cerebellum) = central system agent config attached to a CentralHub.

    Holds config (LLM / tools / prompts / runtime hints) for the CentralHub's
    systemic agent. ``is_active`` enforces "only one active agent per hub"
    via application-layer logic + a partial unique index.
    """

    __tablename__ = "cerebellum_agents"
    __table_args__ = (
        Index(
            "uq_cerebellum_agents_active",
            "central_hub_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND is_active = true"),
        ),
    )

    central_hub_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("blackboards.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CerebellumAgentType.orchestrator.value,
    )
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} hub={self.central_hub_id!r}"
            f" type={self.agent_type!r} active={self.is_active!r}>"
        )
