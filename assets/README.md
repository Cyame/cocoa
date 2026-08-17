# Eyot art assets (pre-visual refresh)

Generated via MiniMax `image-01`. Not fully wired into Portal yet.

## Scope (v0)

| 对象 | 现阶段 | 以后（不急） |
|------|--------|----------------|
| **用户 avatar** | 在 `user-avatars/preset-*.jpg` 里换预设 | 自己上传 / 截图裁剪 |
| **眷族 avatar** | 在 `entity-avatars/preset-*.jpg` 里换色预设 | 上传或 per-entity 覆盖 |
| **神职** | `base-classes/{slug}.jpg`（每职必有 + alt） | 主视觉改版时整体替换 |

权威清单：[`presets.json`](presets.json)。

## Layout

| Path | Purpose |
|------|---------|
| `user-avatars/preset-01…08.jpg` | **用户**可切换预设（默认用 `preset-01`） |
| `user-avatars/pool-*.jpg` | 备用池，未进官方预设 |
| `entity-avatars/preset-*-{tint}.jpg` | **眷族**可切换换色预设（8 个） |
| `entity-avatars/pool-*.jpg` | 眷族换色备用 |
| `base-classes/{slug}.jpg` | 选定后的神职主图（可从 candidates 挑） |
| `base-classes/candidates/{slug}/v2-NN.jpg` | **候选池**（每职 ≥5；无框无水印；API 下线前多存） |
| `base-classes/candidates/_internal/` | 小脑等内部神职素材（不对用户展示） |
| `backgrounds/` / `misc/` | 登录 / IDE / 空态等氛围图 |
| `avatars/` / `entities/` | 早期生成目录 |

## Regenerate 神职候选

```bash
export MINIMAX_API_KEY='…'   # never commit
ASSET_WORKERS=3 python3 scripts/generate-baseclass-candidates.py
```

选定后：`cp assets/base-classes/candidates/<slug>/v2-0N.jpg assets/base-classes/<slug>.jpg`

## Style lock (v0)

Deep charcoal + muted teal/copper, plain studio backdrop, **no frame / seal / watermark / text**.
Product notes: [`.omo/drafts/baseclass-tags-and-empty-workspace.md`](../.omo/drafts/baseclass-tags-and-empty-workspace.md).
