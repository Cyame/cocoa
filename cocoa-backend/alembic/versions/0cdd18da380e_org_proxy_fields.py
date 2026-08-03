"""org proxy fields

Revision ID: 0cdd18da380e
Revises: 94553816102e
Create Date: 2026-08-03 23:59:30.413779

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0cdd18da380e'
down_revision: Union[str, None] = '94553816102e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Existence guards — this revision must run on BOTH paths:
#   A) a database at 94553816102e (proxy columns do not exist yet), and
#   B) a fresh database where b1c2d3e4f5a6 already rebuilt the full schema
#      from live model metadata (Base.metadata.create_all), which pre-creates
#      organizations.use_proxy / proxy_* alongside the base columns.
# ---------------------------------------------------------------------------

_PROXY_COLUMNS = [
    ("use_proxy", sa.Boolean(), "false"),
    ("proxy_host", sa.String(length=255), None),
    ("proxy_port", sa.Integer(), None),
    ("proxy_username", sa.String(length=255), None),
    ("proxy_password", sa.Text(), None),
]


def _has_column(bind, table: str, column: str) -> bool:
    if table not in set(sa.inspect(bind).get_table_names()):
        return False
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    for name, col_type, server_default in _PROXY_COLUMNS:
        if _has_column(bind, "organizations", name):
            continue
        kwargs = {"nullable": True}
        if server_default is not None:
            kwargs["nullable"] = False
            kwargs["server_default"] = sa.text(server_default)
        op.add_column("organizations", sa.Column(name, col_type, **kwargs))


def downgrade() -> None:
    bind = op.get_bind()
    for name, _, _ in reversed(_PROXY_COLUMNS):
        if _has_column(bind, "organizations", name):
            op.drop_column("organizations", name)
