"""remap content ref scopes to hub instance

Revision ID: 1d65b2c05cd1
Revises: a93ee3562177
Create Date: 2026-08-04 20:50:33.717750

v4.5 ContentRef (H7): the canonical scope enum is ``hub | instance``.
Legacy strings persisted inside JSONB payloads are remapped:
``workspace|fornix|vault|blackboard -> hub``, ``memory -> instance``.

Self-contained data migration — must NOT import app code.
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1d65b2c05cd1'
down_revision: Union[str, None] = 'a93ee3562177'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Legacy -> canonical ContentRef scope map (v4.5 H7).
_LEGACY_SCOPE_MAP = {
    "workspace": "hub",
    "fornix": "hub",
    "vault": "hub",
    "blackboard": "hub",
    "memory": "instance",
}

#: SQL prefilter — only rows whose JSONB text contains a ``"scope"`` key
#: are worth decoding (JSONB text renders keys quoted).
_SCOPE_ROWS_SQL = sa.text(
    "SELECT id, payload::text AS payload_text FROM events "
    'WHERE payload::text LIKE \'%"scope"%\''
)
_UPDATE_PAYLOAD_SQL = sa.text(
    "UPDATE events SET payload = CAST(:payload AS jsonb) WHERE id = :id"
)


def _remap_scope(obj):
    """Recursively remap legacy ContentRef scope strings under ``"scope"`` keys.

    Walks arbitrary nested dict/list JSON (event payload shapes are not
    uniform — audit M2).  Only dict entries literally named ``"scope"`` with
    a legacy string value are rewritten; everything else passes through.
    """
    if isinstance(obj, dict):
        return {
            key: (_remap_scope(value) if key != "scope" else _LEGACY_SCOPE_MAP.get(value, value))
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [_remap_scope(item) for item in obj]
    return obj


def _remap_events_payloads(bind) -> int:
    """Remap legacy ContentRef scopes in ``events.payload`` rows.

    Returns the number of rows updated.  ``bind`` is any SQLAlchemy
    connection (sync or async-proxy) usable with ``execute``.
    """
    rows = bind.execute(_SCOPE_ROWS_SQL).fetchall()
    updated = 0
    for row in rows:
        payload = json.loads(row.payload_text)
        new_payload = _remap_scope(payload)
        if new_payload != payload:
            bind.execute(
                _UPDATE_PAYLOAD_SQL,
                {"payload": json.dumps(new_payload, ensure_ascii=False), "id": row.id},
            )
            updated += 1
    return updated


def upgrade() -> None:
    _remap_events_payloads(op.get_bind())


def downgrade() -> None:
    # No-op: the old->new mapping is lossy (workspace/fornix/vault/blackboard
    # all collapse to hub), so a reverse remap cannot recover the original
    # value. Acceptable per v4-5-fornix-hub.md (downgrade is best-effort).
    pass
