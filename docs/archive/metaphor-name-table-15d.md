> **ARCHIVED 2026-08-07 — 15d 命名快照（只读）**
> 本文件为 15d（克苏鲁）命名体系的完整快照，**已被 v5 命名基线取代**。
> 活文档：`docs/metaphor-name-table.md`（v5 映射表）。
> 决策 SoT：`.omo/evidence/v5-rename-decisions.md`。禁止以本文档作为开工命名依据。
> 以下为归档时的原文，完整保留不作修改。
>
> ---
>

> **Pre-v4 reference**: Conflict with `.omo/evidence/audit-product-design.md` → audit wins. Awaiting v4 PRD rewrite.
>

# Eyot Metaphor Name Table (15d)

> **Canonical source**: `.omo/drafts/archive/phase-15d-naming-system.md` §3–§4（已归档；活表为本文件）。
> **Code rename pending**: This table describes the target architecture. Current code (P0-P15b) still uses old naming.

## Preamble

Eyot uses a **two-axis naming system**: backend uses strict technical English, frontend uses Cthulhu/Lovecraft-themed Chinese. This table is the single source of truth mapping every concept from code-term → frontend display-name. Downstream documents (terminology, domain model, preset manifests, UI) derive their identifiers from the rows below.

Database columns use the backend names. UI labels use the frontend names. Backend code internally uses backend names. DB does NOT store display_name columns — the UI layer resolves display via i18n JSON keys.

---

## Name Table

### Structure Terms (Tenant + Entity Hierarchy)

| Backend (code/DB) | Frontend Display | Old Name (P0-P15) | Description |
|---|---|---|---|
| **Organization** | 世界 | (none / emerging) | Top-level isolation unit. PRD-v2 first-class; singleton default. |
| **Namespace** | 次元 | (none / emerging) | **场景分区**（非 env）：e.g. coding / social-media。Entity 归属层。 |
| **Workspace** | 空间 | Office | 场景内具体工作流（平台 / 系统）。Current "Office" model until rename. |
| **BaseClass** | 神职 | EmployeePreset | Preset template: prompt, commands, tools, provider config. 11 built-in. |
| **Entity** | 眷族 | Employee | **per-Namespace** identity + Memory；跨该场景多个 Workspace 复用。 |
| **Instance** | **看场景**：眷族侧=**化身**；空间与人并列=**迷失者** | Instance (unchanged) | Running pod；生命周期 ≤ 空间；同空间同眷族最多 1 个。不是「化身已废弃」。 |
| **Membership** | （见下行拆分） | Membership (unchanged) | **PRD-v3.4**：产品名不再统称「契印」。`user_id` 行 = 空间 **觉醒者**；`instance_id` 行 = **迷失者**拓扑位。 |
| **NamespaceContract** | 契印 | （new in v3.4） | Namespace ↔ User。**契印只在次元层使用此名。** |
| **Passage** | 通道 | Corridor | Edge between two endpoints in Workspace topology. CorridorNode dropped. |
| **CentralHub** | 主脑 | CentralHub (was Blackboard; semantics: 4 脑区合成容器) | Per-Workspace shared state；含 **CerebellumAgent 1:1**。 |
| **CerebellumAgent** | 小脑 / 中央智能体 | (new / emerging) | 主脑内置系统 agent；不可软删；不进拓扑。 |
| **Vault** | 冰封库 | Vault (unchanged) | Cold archive；v2 = DB KV，远期 MinIO/S3。 |
| **Memory** | 记忆沉淀 | MemoryEntry | Append-only per-Entity memory log (experience/lesson/decision/problem). |
| **Event** | 印痕 | Event (unchanged) | Audit log row. |
| **LoopState** | 心智状态 | InstanceLoopState | Harness runtime state: status, continuations, breakers. |
| **DeployRecord** | 降世记录 | DeployRecord (unchanged) | K8s deployment lifecycle record. |
| **Topology** | 心灵图景 | Topology (unchanged) | Spatial visualization canvas with glow nodes + particle animation. |

### BaseClasses (11 Built-in 神职)

Slug = kebab-case identifier (DB unique). Display = i18n key. Commands = per-class command surface.

| Slug | Display | Role | Commands | omo Agent Source |
|---|---|---|---|---|
| `mi-shi` | 密士 | Strategic planner, plan mode sticky | /plan /decompose /prioritize | Prometheus |
| `huan-ling` | 唤灵 | Intent analysis, pre-planner | /analyze /clarify /propose | Metis |
| `an-xing` | 暗行 | Solo full-stack coder | /plan /execute /build /test | Sisyphus |
| `an-ying` | 暗影 | Junior coder, cheap/fast | /execute /build /test | Sisyphus-Junior |
| `zhu-jin` | 铸金 | Autonomous deep worker, goal-driven | /execute /build /test | Hephaestus |
| `ling-shi` | 灵视 | Read-only architecture / debugging | /analyze /predict /review | Oracle |
| `heng-pan` | 衡判 | Quality gate: review/approve/reject | /review /approve /reject | Momus |
| `you-hun` | 游魂 | Codebase grep / exploration | /search /survey /report | Explore |
| `qian-zhi` | 潜知 | External reference + multi-repo + docs | /search /reference /survey | Librarian |
| `bai-tong` | 百瞳 | Visual / media / audio analysis | /look /analyze /describe | Multimodal-Looker |
| `jiu-ri` | 旧日 | Top-level delegation / monitoring | /delegate /monitor /approve | Atlas |

**Gap note**: All 11 omo non-Sisyphus-Junior agents are now BaseClasses. Human operators are users, not a BaseClass. `User.is_super_admin` covers some Atlas semantics, but Atlas itself remains a distinct BaseClass.

### Lab Ranks (克苏鲁神秘系)

Progression from shallow perception → deep knowledge → awakened mastery.

| Backend | Display | Description |
|---|---|---|
| Intern | 浅识者 | Stateless hot-load, no memory, fresh invocation each time. Barely glimpsed the cosmic truth. |
| Researcher | 深潜者 | Full BaseClass + memory, persistent, accumulates experience across invocations. Diving ever deeper. |
| Director | 觉醒者 | Human operator, highest authority, approval and forwarding rights. Fully awakened to direct others. |

### Sub-entities (Data Layer, No Display Name)

| Backend | Old Name | Description |
|---|---|---|
| User | User (unchanged) | Human auth identity |
| BaseClass | EmployeePreset | Persisted preset: slug, manifest JSONB, version |
| Entity | Employee | Per-Workspace identity with BaseClass ref + memory |
| Membership | Membership (unchanged) | Workspace presence: user=觉醒者, instance=迷失者拓扑位 (PRD-v3.4) |
| NamespaceContract | （new） | Namespace ↔ User 契印 |
| BlackboardFile | BlackboardFile (unchanged) | File on a Blackboard |
| VaultEntry | VaultEntry (unchanged) | Archived entry in Vault |
| Memory | MemoryEntry | Append-only memory log per Entity |
| InstanceProviderConfig | InstanceProviderConfig (unchanged) | LLM provider config (internal, no UI) |

---

## Design Rules

1. **Slug = unique identifier (DB layer)**. Display = i18n key (UI layer). DB does not store display_name columns.
2. **Backend code uses backend names**. Frontend UI uses display names resolved from i18n.
3. **Decision rule**: If a concept is not in this table, it doesn't exist yet.
4. **CorridorNode dropped in 15d** — edges simplified to any two points connecting directly. No intermediary anchor nodes.
5. **6 old presets deprecated** — replaced by 11 BaseClasses. Old P1 slugs (mi-shi, zhu-jin, ling-shi, you-hun, heng-pan) retained; new slugs (huan-ling, an-xing, an-ying, qian-zhi, bai-tong, jiu-ri) added. zong-jian (总监) retired as a preset.
6. **Distillation actions** — Instance→Entity = 晋升 (promotion, in-place capture); Entity→BaseClass = 炼化 (transmutation, creates new reusable 神职).

---

*Derived from `.omo/drafts/archive/phase-15d-naming-system.md` §3-§4 (2026-07-28).*
