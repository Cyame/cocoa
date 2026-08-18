# Release Notes

All notable changes to **Eyot** are documented here.

**Convention.** Tags are cut per `x.x` (major.minor). Development builds such
as `0.5.2.dev1` do **not** get their own sections — they fold into the section
for the version they will become. The first tagged release is **1.0**.

---

## Unreleased — targeting 1.0

### 2026-08-17 — Cocoa → Eyot (project rebirth)

The project was **renamed from *Cocoa* to *Eyot*** and reset for a clean
pre-1.0 trajectory.

- **Rename**: product, repo namespace, packages (`eyot-backend` /
  `eyot-portal` / `eyot-instance-host`), and directories.
  The acronym **E·Y·O·T = Entity · Yoke · Organization · Topology**.
- **Version reset**: 5.2.1 → **0.5.2.dev1** (pre-1.0; tags will start at 1.0).
- **0.x generation framing**: 版本轨重置为 **0.x pre-1.0**，正式 tag 从 1.0 起；MINOR 每完成一个切片 +1。
  已交付切片等价映射：**0.4.x ≈ v4 功能收口**、**0.5.0 = v5.0 命名**、**0.5.1 = v5.1 定义**、
  **0.5.2 = v5.2 UIUX**（v5 世代实现已落地，改名重置后以 0.x 编号）。**当前 active = 0.5.3（v5.3 视觉波）**。
- **Alembic reset**: the 35 incremental migration files were squashed into a
  single **schema-only baseline** (`Base.metadata.create_all`).
- **Seeding moved to the app layer**: a fresh database is now populated at
  startup by an idempotent seeder (default 大陆 + 区域, 5 built-in 始祖,
  the internal 小脑, 16 `can_*` permission atoms, `cmd-*` capabilities),
  mirroring the previous migration-seeded data. Alembic stays schema-only.
- **Internal identifiers**: `COCOA_*` env vars → `EYOT_*`, DBs
  `cocoa_dev`/`cocoa_test_*` → `eyot_dev`/`eyot_test_*`, in-cluster DNS,
  knowledge slugs, `CocoaError` → `EyotError`.
- **Tests**: full backend suite green (**1047 passed / 1 skipped**);
  portal lint + build + **264 vitest tests** green.

### 2026-08-17 — 0.5.2.dev2（cocoa 残留对齐）

- 全量对齐文档中的 `cocoa` 残留为 `eyot`：`.omo/` 活跃 + 归档（plans / evidence /
  drafts / notepads）、`docs/archive/`（`docs/roadmap.md` 改名叙事句保留 `Cocoa → Eyot` 原意，仅修语义）。
- 重命名 8 个 `cocoa-*.md` 证据/归档文档为 `eyot-*.md` 并更新全部交叉引用
  （capability-map / capability-gap-table / vs-nodeskclaw-drift / deployment-state +
  archive 的 roadmap / v2-roadmap / v2-program / capability-map-p0-p10-snapshot）。
- `.github/workflows/ci.yml` 内 `cocoa-backend`/`cocoa-portal` → `eyot-backend`/`eyot-portal`
  （CI 路径修复，本地生效；`.github/` 仍按 `.gitignore` 不追踪）。
- 上述 `.omo/`、`AGENTS.md`、`.github/` 改动为本地态（gitignored，不入库）；
  本 commit 仅含 `docs/archive/` 12 个追踪文档。版号 0.5.2.dev1 → **0.5.2.dev2**。

### 2026-08-18 — 后端测试隔离

- pytest 启动时清除宿主机的 HTTP/HTTPS/SOCKS 代理变量，避免 mock 的
  LLM 测试因本地代理缺少 `socksio` 而在客户端构造阶段失败。
- 新增测试环境回归覆盖；后端全量测试为 **1051 passed / 1 skipped**。
- Portal、Backend、Instance Host 的版本号统一到 `0.5.2.dev3`。
- OrbStack 中旧 Cocoa Portal 占用 `30173` 时，Eyot Portal 改用空闲 NodePort `30174`。

## 1.0

_To be tagged. Sections for 1.x releases land here; `*.devN` builds above fold
into them._

## Template (new x.x release)

```markdown
## x.y — <date>

### Added
- ...

### Changed
- ...

### Fixed
- ...
```
