"""add fornix_files content

Revision ID: a93ee3562177
Revises: f2dc5f8eee1a
Create Date: 2026-08-04 17:52:11.364623

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a93ee3562177'
down_revision: Union[str, None] = 'f2dc5f8eee1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The PRD-v2 rebuild baseline (b1c2d3e4f5a6) runs create_all against the
    # *current* model metadata, so on a fresh DB `content` already exists there;
    # only add it when upgrading a pre-v4.5 schema that lacks the column.
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("fornix_files")}
    if "content" not in columns:
        op.add_column('fornix_files', sa.Column('content', sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("fornix_files")}
    if "content" in columns:
        op.drop_column('fornix_files', 'content')
