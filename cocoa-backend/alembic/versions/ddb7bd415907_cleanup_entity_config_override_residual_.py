"""cleanup entity config_override residual manifest mirrors

Revision ID: ddb7bd415907
Revises: 9536991c7a95
Create Date: 2026-08-05 15:35:14.310928

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'ddb7bd415907'
down_revision: Union[str, None] = '9536991c7a95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # v4.9.1 cross-ref L20: drop residual manifest-mirror arrays (skills /
    # tools / commands) from Entity.config_override. v4.0 moved the write
    # truth to the junction tables (entities.py strips cap keys on write);
    # these mirror BaseClass.manifest content and have no runtime reader in
    # overlay.py. Cap keys + runtime config keys keep their overlay semantics
    # and are retained. Idempotent: existence check makes a re-run a no-op.
    op.execute(
        sa.text(
            "UPDATE entities "
            "SET config_override = "
            "    config_override - 'skills' - 'tools' - 'commands' "
            "WHERE deleted_at IS NULL "
            "AND jsonb_typeof(config_override) = 'object' "
            "AND (config_override ? 'skills' "
            "     OR config_override ? 'tools' "
            "     OR config_override ? 'commands')"
        )
    )


def downgrade() -> None:
    """No reverse: removed mirror keys are derived aggregates; the junction
    tables remain the source of truth and any consumer re-derives them."""
