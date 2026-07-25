"""Instance model — a workspace runtime for an employee in an office."""

from enum import Enum

from sqlalchemy import JSON, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import BaseModel


class InstanceStatus(str, Enum):
    """Lifecycle states for an Instance.

    States:
        creating: Infrastructure provisioning in progress.
        pending: Provisioned, waiting for agent assignment.
        deploying: Agent image pulling and container startup.
        running: Agent is operational and accepting commands.
        restarting: Agent is being restarted (e.g. config change).
        failed: Provisioning, deployment, or runtime error.
        deleting: Instance is being torn down.
    """

    creating = "creating"
    pending = "pending"
    deploying = "deploying"
    running = "running"
    restarting = "restarting"
    failed = "failed"
    deleting = "deleting"


class Instance(BaseModel, Base):
    """A workspace runtime associated with an employee in a specific office.

    One employee can have multiple instances (e.g. different offices, or
    multiple workspaces in the same office).  workspace_path is unique
    among active (non-deleted) instances.
    """

    __tablename__ = "instances"
    __table_args__ = (
        Index(
            "uq_instances_workspace_path",
            "workspace_path",
            unique=True,
            postgresql_where=text(
                "deleted_at IS NULL AND workspace_path IS NOT NULL"
            ),
        ),
    )

    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id"), nullable=False
    )
    office_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("offices.id"), nullable=False
    )
    workspace_path: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=InstanceStatus.creating.value
    )
    # Langfuse integration (P8 agent runtime reads from instance runtime_config):
    #   Reserved keys in runtime_config dict:
    #     langfuse_enabled: bool
    #     langfuse_public_key: str
    #     langfuse_secret_key: str
    #     langfuse_host: str
    runtime_config: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    proxy_token: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )

    def __repr__(self) -> str:
        cls = type(self).__name__
        return (
            f"<{cls} {self.id!r} employee={self.employee_id!r}"
            f" office={self.office_id!r} status={self.status!r}>"
        )
