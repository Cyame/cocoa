"""rename memberships coord columns to posx posy

P9 Todo 1: rename ``Membership.hex_q`` / ``Membership.hex_r`` to
``Membership.posx`` / ``Membership.posy`` to move from a hex-coordinate
vocabulary (q, r) to a free Cartesian vocabulary (posx, posy). This is
a data-preserving rename via ``op.alter_column(new_column_name=...)``
and not a DROP + ADD (autogenerate cannot detect renames and would
silently destroy coordinate data).

Also adds a partial unique index ``uq_memberships_office_pos`` on
(office_id, posx, posy) WHERE deleted_at IS NULL, so two active
memberships in the same office cannot occupy the same (posx, posy)
cell. Soft-deleted rows remain reusable for reactivation, as with all
other Cocoa partial unique indexes.

Revision ID: 24ba2c528d6e
Revises: bc3d9d6a84c8
Create Date: 2026-07-27 10:38:39.881075

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "24ba2c528d6e"
down_revision: Union[str, None] = "bc3d9d6a84c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Rename hex_q -> posx (preserves data; NOT null constraint stays).
    op.alter_column(
        "memberships",
        "hex_q",
        new_column_name="posx",
    )
    # 2. Rename hex_r -> posy (preserves data; NOT null constraint stays).
    op.alter_column(
        "memberships",
        "hex_r",
        new_column_name="posy",
    )
    # 3. Add partial unique index on (office_id, posx, posy) for active rows.
    #    Mirrors the naming pattern of uq_memberships_office_user and
    #    uq_memberships_office_instance. Constraint is partial because
    #    soft-deleted memberships should remain re-creatable at the
    #    same coords (P5 soft-delete contract).
    op.create_index(
        "uq_memberships_office_pos",
        "memberships",
        ["office_id", "posx", "posy"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    # Inverse of upgrade: drop the new index, then rename columns back.
    op.drop_index(
        "uq_memberships_office_pos",
        table_name="memberships",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.alter_column(
        "memberships",
        "posy",
        new_column_name="hex_r",
    )
    op.alter_column(
        "memberships",
        "posx",
        new_column_name="hex_q",
    )
