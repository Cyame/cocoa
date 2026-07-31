"""passage_mode_dual_normalize

Revision ID: 592642a40460
Revises: b4b81cf04926
Create Date: 2026-07-31 10:52:59.834396

Idempotent: ``b1c2d3e4f5a6`` rebuilds from live SQLAlchemy metadata, so a
fresh upgrade already creates ``passages.mode`` before this revision runs.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "592642a40460"
down_revision: Union[str, None] = "b4b81cf04926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("passages")}
    if "mode" not in cols:
        op.add_column(
            "passages",
            sa.Column(
                "mode",
                sa.String(length=16),
                server_default="dual",
                nullable=False,
            ),
        )

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT id, workspace_id, from_membership_id, to_membership_id,
                   created_at, updated_at
            FROM passages
            WHERE deleted_at IS NULL
            """
        )
    ).mappings().all()

    groups: dict[tuple[str, frozenset[str]], list] = defaultdict(list)
    for row in rows:
        key = (
            row["workspace_id"],
            frozenset({row["from_membership_id"], row["to_membership_id"]}),
        )
        groups[key].append(row)

    now = datetime.now(timezone.utc)
    for (_ws, _pair), members in groups.items():
        members_sorted = sorted(
            members,
            key=lambda r: (r["updated_at"] or r["created_at"] or now),
            reverse=True,
        )
        keeper = members_sorted[0]
        for dup in members_sorted[1:]:
            conn.execute(
                sa.text(
                    """
                    UPDATE passages
                    SET deleted_at = :now, is_active = false, updated_at = :now
                    WHERE id = :id AND deleted_at IS NULL
                    """
                ),
                {"now": now, "id": dup["id"]},
            )

        a = keeper["from_membership_id"]
        b = keeper["to_membership_id"]
        lo, hi = (a, b) if a <= b else (b, a)
        conn.execute(
            sa.text(
                """
                UPDATE passages
                SET from_membership_id = :lo,
                    to_membership_id = :hi,
                    mode = 'dual',
                    updated_at = :now
                WHERE id = :id
                """
            ),
            {"lo": lo, "hi": hi, "now": now, "id": keeper["id"]},
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("passages")}
    if "mode" in cols:
        op.drop_column("passages", "mode")
