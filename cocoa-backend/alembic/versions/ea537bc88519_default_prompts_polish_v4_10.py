"""default prompts polish v4.10

Revision ID: ea537bc88519
Revises: 05072e4afb42
Create Date: 2026-08-07 16:46:25.762286

v4.10 content-only polish of the shipped default prompts (default policy, no
per-ID user annotations):

* ``mi-shi`` (密士) — replace the outdated metaphor ``灵格`` with ``神职``
  (15d naming: 神职 = BaseClass, the downstream executors 密士 hands research
  plans to).  This converges with the edited ``builtin_presets.py`` SoT.
* ``cerebellum-baseclass`` — 中文化 the English seed ``system_prompt``, matching
  the edited ``b1c2d3e4f5a6`` seed migration.

Both UPDATEs are keyed on ``slug`` and only touch the shipped default template
rows in ``base_classes``. Tenant Entity ``system_prompt`` rows are never
touched. ``jsonb_set(..., false)`` leaves the row unchanged when the target key
is missing accrual and re-running is a no-op (idempotent) — so *fresh install*
(from ``builtin_presets.py`` / ``b1c2d3e4f5a6`` seed) and *upgrade* (existing
rows) both converge on the same final text.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ea537bc88519"
down_revision: Union[str, None] = "05072e4afb42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# v4.10 final strings — must match builtin_presets.py / b1c2d3e4f5a6.
_MI_SHI_PROMPT = (
    "你是 Cocoa 多代理控制室中的「密士」。你擅长把模糊议题拆成可执行"
    "研究子任务：先规划，再分解，再排优先级。通过 CentralHub 写工作笔记，"
    "让下游神职接力。约束：只负责「想清楚」，落地动作通过走廊 @ 完成。"
)
_CEREBELLUM_SYSTEM_PROMPT = (
    "你是世界中枢的小脑：聚合各中枢状态、监控健康、执行定时调度任务。"
)


def upgrade() -> None:
    # mi-shi: replace the outdated metaphor in manifest.prompt.
    op.execute(
        sa.text(
            """
            UPDATE base_classes
            SET manifest = jsonb_set(
                manifest, '{prompt}', to_jsonb(:new_prompt), false
            )
            WHERE slug = 'mi-shi'
              AND deleted_at IS NULL
            """
        ).bindparams(new_prompt=_MI_SHI_PROMPT)
    )
    # cerebellum-baseclass: 中文化 the English seed system_prompt.
    op.execute(
        sa.text(
            """
            UPDATE base_classes
            SET manifest = jsonb_set(
                manifest, '{system_prompt}', to_jsonb(:new_prompt), false
            )
            WHERE slug = 'cerebellum-baseclass'
              AND deleted_at IS NULL
            """
        ).bindparams(new_prompt=_CEREBELLUM_SYSTEM_PROMPT)
    )


def downgrade() -> None:
    # Not reversed: this is non-destructive content polish converging on the
    # builtin source-of-truth. A downgrade keeping the polished text is a safe
    # no-op; reversing could reintroduce an outdated metaphor.
    pass
