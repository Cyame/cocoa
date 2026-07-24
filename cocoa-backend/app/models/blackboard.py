"""Blackboard and Vault models — Office-scoped collaboration and archival storage."""

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class Blackboard(BaseModel, Base):
    """1:1 shared collaboration context per Office.

    Each office has exactly one Blackboard. content is the system-generated
    summary; manual_notes are human-annotated notes.
    """

    __tablename__ = "blackboards"
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


class BlackboardFile(BaseModel, Base):
    """A file or directory within a Blackboard's virtual filesystem.

    Files are keyed by storage_key (globally unique, not soft-deleted).
    Directory entries have is_directory=True.
    Uploader is either a human user or an Instance -- enforced via CHECK (XOR).
    """

    __tablename__ = "blackboard_files"
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

    blackboard_file = "blackboard_file"
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
