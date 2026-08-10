"""v5.1 M1 backfill subagent_strategy into 5 始祖 manifests

Revision ID: b49542153efc
Revises: 78137b7985e5
Create Date: 2026-08-09 14:14:18.395859

存量库 backfill（`.omo/plans/v5-1-definition.md` TODO #3 M1）：
5 始祖（fox/beaver/sparrow/coyote/lion）的 base_classes.manifest 若由 v5.0
（78137b7985e5）写入，则不含 v5.1 新增的 subagent_strategy。本迁移以
``app.core.builtin_presets``（SoT，T2 已落地）为唯一值来源，对每个始祖执行
幂等 JSONB merge：

    manifest = COALESCE(manifest, '{}'::jsonb) || {"subagent_strategy": strategy}

JSONB concat 右值覆盖左值同名 key，同值覆盖无害 → 天然幂等（重复执行结果相同）：

- fresh 库：seed（51e780f715e0 live-import ALL_BUILTIN_PRESETS）已带
  subagent_strategy → 同值覆盖，结果不变
- 存量库：首次补齐该 key
- 值来源单一：运行时读取活代码，与 fresh 路径（seed）同 SoT，无硬编码副本

值过滤依据：仅 5 始祖 manifest 含 subagent_strategy（zong-jian provider=None
不带该 key），按 key 存在性过滤即精确得到 5 始祖，无需维护 slug 清单。
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b49542153efc'
down_revision: Union[str, None] = '78137b7985e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.core.builtin_presets import ALL_BUILTIN_PRESETS

    # 运行时从 SoT 读取：slug → subagent_strategy（仅 5 始祖携带）
    strategies = {
        preset["slug"]: preset["manifest"]["subagent_strategy"]
        for preset in ALL_BUILTIN_PRESETS
        if "subagent_strategy" in preset["manifest"]
    }

    conn = op.get_bind()
    for slug, strategy in strategies.items():
        conn.execute(
            sa.text(
                "UPDATE base_classes "
                "SET manifest = COALESCE(manifest, '{}'::jsonb) || CAST(:strategy AS jsonb), "
                "updated_at = now() "
                "WHERE slug = :slug AND deleted_at IS NULL"
            ),
            {"strategy": json.dumps({"subagent_strategy": strategy}), "slug": slug},
        )


def downgrade() -> None:
    # 幂等 backfill 不回退：fresh 库该 key 由 seed（51e780f715e0）写入，downgrade
    # 剥离会破坏 fresh/存量两路径一致性；同值覆盖无副作用，保持只读。
    pass
