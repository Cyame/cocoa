"""add composer_messages table

Revision ID: b4b81cf04926
Revises: ad2e3fb35866
Create Date: 2026-07-31 08:18:06.255556

Idempotent: ``b1c2d3e4f5a6`` rebuilds from live SQLAlchemy metadata, so a
fresh upgrade already creates ``composer_messages`` before this revision runs.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4b81cf04926"
down_revision: Union[str, None] = "ad2e3fb35866"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "composer_messages" not in tables:
        op.create_table(
            "composer_messages",
            sa.Column("namespace_id", sa.String(length=36), nullable=False),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("target_entity", sa.String(length=255), nullable=True),
            sa.Column("instance_id", sa.String(length=36), nullable=True),
            sa.Column("turn_id", sa.String(length=36), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("author_user_id", sa.String(length=36), nullable=True),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["author_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["instance_id"], ["instances.id"]),
            sa.ForeignKeyConstraint(["namespace_id"], ["namespaces.id"]),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    tables = set(sa.inspect(bind).get_table_names())
    if "composer_messages" not in tables:
        return

    indexes = {ix["name"] for ix in sa.inspect(bind).get_indexes("composer_messages")}
    if "ix_composer_messages_namespace" not in indexes:
        op.create_index(
            "ix_composer_messages_namespace",
            "composer_messages",
            ["namespace_id"],
            unique=False,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
    if "ix_composer_messages_workspace_created" not in indexes:
        op.create_index(
            "ix_composer_messages_workspace_created",
            "composer_messages",
            ["workspace_id", "created_at"],
            unique=False,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "composer_messages" not in set(inspector.get_table_names()):
        return
    indexes = {ix["name"] for ix in inspector.get_indexes("composer_messages")}
    if "ix_composer_messages_workspace_created" in indexes:
        op.drop_index(
            "ix_composer_messages_workspace_created",
            table_name="composer_messages",
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
    if "ix_composer_messages_namespace" in indexes:
        op.drop_index(
            "ix_composer_messages_namespace",
            table_name="composer_messages",
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
    op.drop_table("composer_messages")
