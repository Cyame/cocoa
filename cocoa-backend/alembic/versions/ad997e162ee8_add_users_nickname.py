"""add users nickname

Revision ID: ad997e162ee8
Revises: 592642a40460
Create Date: 2026-07-31 18:51:34.771773

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ad997e162ee8"
down_revision: Union[str, None] = "592642a40460"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # b1c2d3e4f5a6 recreate_all may already include nickname when run against
    # a checkout that already has User.nickname on the model.
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("users")}
    if "nickname" not in cols:
        op.add_column(
            "users", sa.Column("nickname", sa.String(length=255), nullable=True)
        )


def downgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("users")}
    if "nickname" in cols:
        op.drop_column("users", "nickname")
