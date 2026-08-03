"""backfill cerebellum baseclass scope system

Revision ID: 794abeff4722
Revises: b3c626105a7e
Create Date: 2026-08-03 21:33:19.389482

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '794abeff4722'
down_revision: Union[str, None] = 'b3c626105a7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # v4.0 backfill (b3c626105a7e) scoped cerebellum-baseclass to 'org' because
    # it is not in PRESET_COMMANDS.keys() (see the NOT-slug-ANY branch). It is an
    # internal/system 神职 (tags=['internal','system']) and must be system-scoped
    # so `include_internal=true` surfaces it to any authenticated user.
    op.execute(
        sa.text(
            "UPDATE base_classes SET scope = 'system', organization_id = NULL,"
            " namespace_id = NULL, updated_at = now()"
            " WHERE slug = 'cerebellum-baseclass' AND deleted_at IS NULL"
        )
    )


def downgrade() -> None:
    # Reverse: restore the v4.0 backfill behavior (org scope on the default org).
    default_org = op.get_bind().execute(
        sa.text(
            "SELECT id FROM organizations WHERE slug = 'default' AND deleted_at IS NULL"
            " LIMIT 1"
        )
    ).fetchone()
    if default_org:
        op.execute(
            sa.text(
                "UPDATE base_classes SET scope = 'org', organization_id = :org,"
                " updated_at = now()"
                " WHERE slug = 'cerebellum-baseclass' AND deleted_at IS NULL"
            ),
            {"org": default_org[0]},
        )
