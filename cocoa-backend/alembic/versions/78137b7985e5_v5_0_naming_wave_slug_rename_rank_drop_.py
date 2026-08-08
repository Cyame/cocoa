"""v5.0 naming wave: slug rename + rank drop + 6 demoted removal

Revision ID: 78137b7985e5
Revises: ea537bc88519
Create Date: 2026-08-08 13:40:57.318201

v5.0 命名波（`.omo/evidence/v5-rename-decisions.md` §四/§六）:
  5 始祖（fox/beaver/sparrow/coyote/lion）替代旧 11 神职中的同名神职；
  6 降级（huan-ling/ling-shi/heng-pan/you-hun/qian-zhi/bai-tong）物理删除。

M1 — slug 幂等双匹配 UPDATE（旧→新，不假设旧 slug 存在）
M2 — 6 降级物理删除（全链路级联：memories→memberships→instances→entities→base_classes）
M3 — DROP entities.rank 列（模型层已删，DB 列还在）
M4 — 修复 b3c626105a7e 冻结快照：新 slug 的 junction 播种 + scope 回填
     （b3c626105a7e 的 PRESET_COMMANDS 硬编码旧 slug，fresh 库 seed 新 slug 后
      junction 为空 + scope 未设为 system）
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '78137b7985e5'
down_revision: Union[str, None] = 'ea537bc88519'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# M1 slug mapping: old → new (5 始祖 renamed)
# ---------------------------------------------------------------------------
_SLUG_RENAME: dict[str, str] = {
    "mi-shi": "fox",
    "an-xing": "beaver",
    "an-ying": "sparrow",
    "zhu-jin": "coyote",
    "jiu-ri": "lion",
}

# M2 6 降级 slugs (physical delete)
_DEMOTED_SLUGS: list[str] = [
    "huan-ling",
    "ling-shi",
    "heng-pan",
    "you-hun",
    "qian-zhi",
    "bai-tong",
]

# M4 new preset commands (frozen v5.0 snapshot, matching BUILTIN_PRESETS)
_NEW_PRESET_COMMANDS: dict[str, list[str]] = {
    "fox": ["plan", "decompose", "prioritize"],
    "beaver": ["plan", "execute", "build", "test"],
    "sparrow": ["execute", "build", "test"],
    "coyote": ["execute", "build", "test"],
    "lion": ["delegate", "monitor", "approve"],
}


def _new_id() -> str:
    return str(uuid.uuid4())


def upgrade() -> None:
    conn = op.get_bind()

    # =====================================================================
    # M1 — slug 幂等双匹配 UPDATE
    # =====================================================================

    # base_classes.slug: match old OR new (idempotent)
    for old, new in _SLUG_RENAME.items():
        conn.execute(
            sa.text(
                "UPDATE base_classes SET slug = :new, updated_at = now()"
                " WHERE slug IN (:old, :new) AND deleted_at IS NULL"
            ),
            {"old": old, "new": new},
        )

    # entities.preset_slug soft-ref: match old OR new
    for old, new in _SLUG_RENAME.items():
        conn.execute(
            sa.text(
                "UPDATE entities SET preset_slug = :new"
                " WHERE preset_slug IN (:old, :new)"
            ),
            {"old": old, "new": new},
        )

    # manifest JSONB source_preset_slug (if present)
    for old, new in _SLUG_RENAME.items():
        conn.execute(
            sa.text(
                "UPDATE base_classes"
                " SET manifest = jsonb_set(manifest, '{source_preset_slug}',"
                " to_jsonb(CAST(:new_val AS text)))"
                " WHERE manifest->>'source_preset_slug' IN (:old, :new_val)"
            ),
            {"old": old, "new_val": new},
        )

    # distilled preset slugs (e.g. mi-shi-skill-xxx → fox-skill-xxx)
    for old, new in _SLUG_RENAME.items():
        conn.execute(
            sa.text(
                "UPDATE base_classes SET slug = replace(slug, :old, :new)"
                " WHERE slug LIKE :pattern AND deleted_at IS NULL"
            ),
            {"old": old, "new": new, "pattern": f"{old}-skill-%"},
        )

    # display_name i18n key 化
    _DISPLAY_KEYS: dict[str, str] = {
        "fox": "baseClass.display.fox",
        "beaver": "baseClass.display.beaver",
        "sparrow": "baseClass.display.sparrow",
        "coyote": "baseClass.display.coyote",
        "lion": "baseClass.display.lion",
    }
    for slug, key in _DISPLAY_KEYS.items():
        conn.execute(
            sa.text(
                "UPDATE base_classes SET display_name = :key, updated_at = now()"
                " WHERE slug = :slug AND deleted_at IS NULL"
            ),
            {"slug": slug, "key": key},
        )

    # =====================================================================
    # M2 — 6 降级物理删除（全链路级联）
    # =====================================================================
    _DEMOTED = tuple(_DEMOTED_SLUGS)

    # Get demoted base_class IDs (before deleting them)
    demoted_bc_rows = conn.execute(
        sa.text(
            "SELECT id FROM base_classes WHERE slug = ANY(:slugs)"
        ),
        {"slugs": list(_DEMOTED)},
    ).fetchall()
    demoted_bc_ids = [row[0] for row in demoted_bc_rows]

    # Get entity IDs for demoted presets
    demoted_entities = conn.execute(
        sa.text(
            "SELECT id FROM entities WHERE preset_slug = ANY(:slugs)"
        ),
        {"slugs": list(_DEMOTED)},
    ).fetchall()
    demoted_entity_ids = [row[0] for row in demoted_entities]

    if demoted_entity_ids:
        # Instance IDs for demoted entities
        demoted_instances = conn.execute(
            sa.text(
                "SELECT id FROM instances WHERE entity_id = ANY(:eids)"
            ),
            {"eids": demoted_entity_ids},
        ).fetchall()
        demoted_instance_ids = [row[0] for row in demoted_instances]

        # entity_ai_genes junctions
        conn.execute(
            sa.text("DELETE FROM entity_ai_genes WHERE entity_id = ANY(:eids)"),
            {"eids": demoted_entity_ids},
        )
        # entity_capabilities junctions
        conn.execute(
            sa.text("DELETE FROM entity_capabilities WHERE entity_id = ANY(:eids)"),
            {"eids": demoted_entity_ids},
        )
        # memories
        conn.execute(
            sa.text("DELETE FROM memories WHERE entity_id = ANY(:eids)"),
            {"eids": demoted_entity_ids},
        )
        # memberships
        if demoted_instance_ids:
            conn.execute(
                sa.text("DELETE FROM memberships WHERE instance_id = ANY(:iids)"),
                {"iids": demoted_instance_ids},
            )
        # instances
        conn.execute(
            sa.text("DELETE FROM instances WHERE entity_id = ANY(:eids)"),
            {"eids": demoted_entity_ids},
        )
        # entities
        conn.execute(
            sa.text("DELETE FROM entities WHERE id = ANY(:eids)"),
            {"eids": demoted_entity_ids},
        )

    # base_class_capabilities junctions (references demoted base_classes)
    if demoted_bc_ids:
        conn.execute(
            sa.text(
                "DELETE FROM base_class_capabilities WHERE base_class_id = ANY(:bids)"
            ),
            {"bids": demoted_bc_ids},
        )

    # base_classes (demoted slugs)
    conn.execute(
        sa.text(
            "DELETE FROM base_classes WHERE slug = ANY(:slugs)"
        ),
        {"slugs": list(_DEMOTED)},
    )

    # =====================================================================
    # M3 — DROP entities.rank 列（幂等）
    # =====================================================================
    insp = sa.inspect(conn)
    if "rank" in {c["name"] for c in insp.get_columns("entities")}:
        op.drop_column("entities", "rank")

    # =====================================================================
    # M4 — 修复 b3c626105a7e 冻结快照：新 slug junction + scope 回填
    # =====================================================================

    # M4a. scope 回填：5 新 slug 设为 system（幂等）
    new_slugs = tuple(_NEW_PRESET_COMMANDS.keys())
    conn.execute(
        sa.text(
            "UPDATE base_classes SET scope = 'system', organization_id = NULL,"
            " namespace_id = NULL, updated_at = now()"
            " WHERE slug = ANY(:slugs) AND deleted_at IS NULL"
            " AND (scope IS NULL OR scope != 'system')"
        ),
        {"slugs": list(new_slugs)},
    )

    # M4b. junction 播种：cmd-* capabilities → base_class_capabilities
    # cmd-* capabilities already exist from b3c626105a7e (same verb set).
    # Only need to create the missing base_class_capabilities junctions.
    cmd_cap_ids: dict[str, str] = {}
    for verb in sorted({v for verbs in _NEW_PRESET_COMMANDS.values() for v in verbs}):
        name = f"cmd-{verb}"
        row = conn.execute(
            sa.text("SELECT id FROM capability_market WHERE name = :n AND deleted_at IS NULL"),
            {"n": name},
        ).fetchone()
        if row:
            cmd_cap_ids[verb] = row[0]

    for slug, verbs in _NEW_PRESET_COMMANDS.items():
        bc = conn.execute(
            sa.text("SELECT id FROM base_classes WHERE slug = :s AND deleted_at IS NULL"),
            {"s": slug},
        ).fetchone()
        if not bc:
            continue
        for verb in verbs:
            cap_id = cmd_cap_ids.get(verb)
            if cap_id is None:
                continue
            exists = conn.execute(
                sa.text(
                    "SELECT 1 FROM base_class_capabilities"
                    " WHERE base_class_id = :bc AND capability_id = :cap"
                    " AND deleted_at IS NULL"
                ),
                {"bc": bc[0], "cap": cap_id},
            ).fetchone()
            if not exists:
                conn.execute(
                    sa.text(
                        "INSERT INTO base_class_capabilities"
                        " (id, base_class_id, capability_id, created_at, updated_at)"
                        " VALUES (:id, :bc, :cap, now(), now())"
                    ),
                    {"id": _new_id(), "bc": bc[0], "cap": cap_id},
                )


def downgrade() -> None:
    """v5.0 naming wave is not reversible (physical deletes + DROP column)."""
    raise NotImplementedError(
        "v5.0 naming wave downgrade not supported:"
        " physical deletes + DROP column are irreversible"
    )