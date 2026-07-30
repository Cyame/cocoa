"""prd_v3_4_namespace_contracts_and_instance_unique

Revision ID: ad2e3fb35866
Revises: 6b5e1ccff9ae
Create Date: 2026-07-30 19:14:32.886363

Idempotent: ``b1c2d3e4f5a6`` rebuilds from live SQLAlchemy metadata, so a
fresh upgrade already creates these objects before this revision runs.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "ad2e3fb35866"
down_revision: Union[str, None] = "6b5e1ccff9ae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "namespace_contracts" not in tables:
        op.create_table(
            "namespace_contracts",
            sa.Column("namespace_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column(
                "permissions",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
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
            sa.ForeignKeyConstraint(["namespace_id"], ["namespaces.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    contract_indexes = {
        ix["name"] for ix in inspector.get_indexes("namespace_contracts")
    } if "namespace_contracts" in set(sa.inspect(bind).get_table_names()) else set()
    if "uq_namespace_contracts_ns_user" not in contract_indexes:
        op.create_index(
            "uq_namespace_contracts_ns_user",
            "namespace_contracts",
            ["namespace_id", "user_id"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )

    instance_indexes = {ix["name"] for ix in inspector.get_indexes("instances")}
    if "uq_instances_workspace_entity" not in instance_indexes:
        op.create_index(
            "uq_instances_workspace_entity",
            "instances",
            ["workspace_id", "entity_id"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )


def downgrade() -> None:
    op.drop_index(
        "uq_instances_workspace_entity",
        table_name="instances",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(
        "uq_namespace_contracts_ns_user",
        table_name="namespace_contracts",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("namespace_contracts")
