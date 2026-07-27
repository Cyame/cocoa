"""add corridor nodes and polymorphic corridors

P9 Todo 8 introduces :class:`app.models.corridor_node.CorridorNode`
— a first-class canvas element that the P9 topology viz can attach
corridors to (mirrors nodeskclaw's ``CorridorHex``).

The Corridor model is also extended to support **polymorphic
endpoints**: each side of an edge is now either a Membership (the
P5 contract) or a CorridorNode. Two new nullable FK columns
(``from_corridor_node_id`` / ``to_corridor_node_id``) are added, the
two legacy columns are made nullable, and CHECK constraints enforce
"exactly one of (membership, node) non-null per side".

A partial unique index ``uq_corridor_nodes_office_pos`` on
(office_id, posx, posy) WHERE deleted_at IS NULL keeps the
CorridorNode canvas cells non-overlapping, mirroring
``uq_memberships_office_pos`` for Memberships.

The body is hand-written because ``--autogenerate`` cannot reason
about CHECK constraints or about making existing NOT NULL columns
nullable while preserving data — it would either silently drop the
data or generate a destructive migration.

Revision ID: fafeb9d6f27a
Revises: 24ba2c528d6e
Create Date: 2026-07-27 12:54:28.298731

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "fafeb9d6f27a"
down_revision: Union[str, None] = "24ba2c528d6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. New corridor_nodes table. Mirrors the Membership columns that
    #    the partial unique index needs (office_id, posx, posy) plus
    #    the corridor-node-only fields: display_name, optional
    #    glow_color override, lifecycle status, optional created_by FK.
    op.create_table(
        "corridor_nodes",
        sa.Column("office_id", sa.String(length=36), nullable=False),
        sa.Column("posx", sa.Integer(), nullable=False),
        sa.Column("posy", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("glow_color", sa.String(length=7), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
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
        sa.ForeignKeyConstraint(["office_id"], ["offices.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_corridor_nodes_office_pos",
        "corridor_nodes",
        ["office_id", "posx", "posy"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # 2. Corridor polymorphic: add corridor_node FK columns.
    op.add_column(
        "corridors",
        sa.Column(
            "from_corridor_node_id",
            sa.String(length=36),
            nullable=True,
        ),
    )
    op.add_column(
        "corridors",
        sa.Column(
            "to_corridor_node_id",
            sa.String(length=36),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_corridors_from_corridor_node",
        "corridors",
        "corridor_nodes",
        ["from_corridor_node_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_corridors_to_corridor_node",
        "corridors",
        "corridor_nodes",
        ["to_corridor_node_id"],
        ["id"],
    )

    # 3. Make the legacy membership FK columns nullable so the
    #    polymorphic CHECK constraint can be satisfied by either
    #    endpoint type. Existing rows keep their values (no rewrite
    #    needed — only the NOT NULL constraint is dropped).
    op.alter_column("corridors", "from_membership_id", nullable=True)
    op.alter_column("corridors", "to_membership_id", nullable=True)

    # 4. Polymorphic CHECK constraints: exactly one of (membership,
    #    corridor_node) non-null on each side. The ::int casts turn
    #    booleans into 0/1 so we can sum them in a CHECK expression.
    op.create_check_constraint(
        "ck_corridors_from_polymorphic",
        "corridors",
        "(from_membership_id IS NOT NULL)::int"
        " + (from_corridor_node_id IS NOT NULL)::int = 1",
    )
    op.create_check_constraint(
        "ck_corridors_to_polymorphic",
        "corridors",
        "(to_membership_id IS NOT NULL)::int"
        " + (to_corridor_node_id IS NOT NULL)::int = 1",
    )


def downgrade() -> None:
    # Inverse of upgrade: drop CHECKs, drop the corridor_node FK
    # columns, restore NOT NULL on the membership columns, drop the
    # corridor_nodes table. The downgrade assumes no existing rows
    # actually USE the corridor_node endpoints — if they do, the
    # NOT NULL restoration will fail with a constraint violation.
    op.drop_constraint(
        "ck_corridors_to_polymorphic", "corridors", type_="check"
    )
    op.drop_constraint(
        "ck_corridors_from_polymorphic", "corridors", type_="check"
    )
    op.alter_column("corridors", "to_membership_id", nullable=False)
    op.alter_column("corridors", "from_membership_id", nullable=False)
    op.drop_constraint(
        "fk_corridors_to_corridor_node", "corridors", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_corridors_from_corridor_node", "corridors", type_="foreignkey"
    )
    op.drop_column("corridors", "to_corridor_node_id")
    op.drop_column("corridors", "from_corridor_node_id")
    op.drop_index(
        "uq_corridor_nodes_office_pos",
        table_name="corridor_nodes",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("corridor_nodes")
