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