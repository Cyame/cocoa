# Cocoa Metaphor Name Table (v5 山海+生物世界观)

> **Canonical source**: v5 命名基线（2026-08-07 终稿）。决策 SoT：`.omo/evidence/v5-rename-decisions.md`。
> **Prior**: 15d（克苏鲁）命名快照归档于 `docs/archive/metaphor-name-table-15d.md`（只读）。
> **执行波**: v5（`.omo/plans/v5-roadmap.md`）——v5.0 命名波起 UI 显示名逐步切换；后端代码名/DB/API 不动。

## Preamble

Cocoa uses a **two-axis naming system**: backend uses strict technical English, frontend uses 山海+生物（自然地理/动物）世界观 Chinese terms. This table is the single source of truth mapping every concept from code-term → frontend display-name.

Database columns use the backend names. UI labels use the frontend names. Backend code internally uses backend names. DB does NOT store display_name columns — the UI layer resolves display via i18n JSON keys.

---

## Name Table

### Structure Terms（租户 + 实体层级）

| Backend (code/DB) | Frontend Display (v5) | 15d Display（已归档）| Description |
|---|---|---|---|
| **Organization** | **大陆** | 世界 | Top-level isolation unit; 单租户默认 |
| **Namespace** | **区域** | 次元 | **场景分区**（非 env）|
| **Workspace** | **生境** | 空间 | 场景内具体工作流（当前代码 Office）|
| （场景意象）| **迁徙路线** | — | Portal 拓扑背景意象 |
| **BaseClass** | **始祖** | 神职 | Preset template + subagent 策略; 5 built-in |
| **Entity** | **血脉** | 眷族 | per-Namespace identity + Memory（记忆）|
| **Instance** | **后裔** | 化身 | Running pod; 生命周期 ≤ 生境; 同生境同血脉最多 1 个 |
| **Membership** user 行 | **智人** | 觉醒者 | 真人（生物学期人属物种名）|
| **Membership** instance 行 | **生物** | 迷失者 | AI 成员（各动物种）|
| **NamespaceContract** | **成员**（概念化）| 契印 | 用户是某区域的成员，不再造专有名词 |
| **Passage** | **兽道** | 通道 | 拓扑邻接边 |
| **CentralHub** | **信号塔** | 主脑 | 协作中枢；含 CerebellumAgent 1:1 |
| **CerebellumAgent** | 小脑 / 中央智能体 | 小脑 | 主脑内置系统 agent |
| **Fornix** | **粮仓** | 穹窿 | 共享文件区（活跃）|
| **Vault** | **标本** | 冰封库 | Cold archive（DB KV）|
| **Memory** | **记忆** | 记忆沉淀 | Append-only per-Entity memory log |
| **Event** | **足迹** | 印痕 | Audit log row |
| **LoopState** | **心智状态** | 心智状态 | Harness runtime state |
| **DeployRecord** | **诞生记录** | 降世记录 | K8s deployment lifecycle record |
| **Topology** | **领地地图** | 心灵图景 | 空间可视化 canvas |
| **SystemHub** | **星球中枢** | 系统中枢 | Org 级隐式助手（描述生成 / LLM 默认）|
| **IntelligenceProvider** | **智能** | 智能供者 | LLM provider（org 级配置）|
| **AiGene** | **生物基因** | 深海基因 | 血脉能力包（tool/skill/command）|
| **UserGene** | **智人基因** | 用户基因 | 真人权限/能力基因 |

### BaseClasses（5 Built-in 始祖）

Slug = 英文动物名 kebab-case（DB unique）。Display = i18n key。

| Slug (v5) | Display (v5) | 15d Slug（归档）| 15d 名（归档）| Role | omo Agent Source |
|---|---|---|---|---|---|
| `fox` | **狐狸** | mi-shi | 密士 | Strategic planner, plan mode sticky | Prometheus |
| `beaver` | **海狸** | an-xing | 暗行 | Solo full-stack coder | Sisyphus |
| `sparrow` | **麻雀** | an-ying | 暗影 | Junior coder, cheap/fast | Sisyphus-Junior |
| `coyote` | **郊狼** | zhu-jin | 铸金 | Autonomous deep worker | Hephaestus |
| `lion` | **狮子** | jiu-ri | 旧日 | Top-level delegation / monitoring | Atlas |

### 内置 Subagent 能力（v5.1 落实，不命名、不占拓扑、无 Entity 卡片）

| 15d 神职（归档）| 能力角色 | omo Agent Source | 归属 |
|---|---|---|---|
| 唤灵 | Intent analysis, pre-planner | Metis | per-始祖 manifest 声明 |
| 灵视 | Read-only architecture / debugging | Oracle | per-始祖 manifest 声明 |
| 衡判 | Quality gate: review/approve/reject | Momus | per-始祖 manifest 声明 |
| 游魂 | Codebase grep / exploration | Explore | per-始祖 manifest 声明 |
| 潜知 | External reference + multi-repo + docs | Librarian | per-始祖 manifest 声明 |
| 百瞳 | Visual / media / audio analysis | Multimodal-Looker | per-始祖 manifest 声明 |

### Learning 动作

| Backend | 15d 名（归档）| v5 名 | Description |
|---|---|---|---|
| distill | 蒸馏 | **领悟** | Memory（记忆）→ capability（P10「学习」页面同步改「领悟」）|
| promote | 晋升 | **蜕变** | Instance（后裔）→ Entity（血脉）就地增强 |
| transmute | 炼化 | **演化** | Entity（血脉）→ BaseClass（始祖）新始祖诞生 |

### Sub-entities（Data Layer, No Display Name）

| Backend | Old Name | Description |
|---|---|---|
| User | User (unchanged) | Human auth identity |
| BaseClass | EmployeePreset | Persisted preset: slug, manifest JSONB, version |
| Entity | Employee | Per-Namespace identity with BaseClass ref + memory |
| Membership | Membership (unchanged) | Workspace presence: user=智人, instance=生物 |
| NamespaceContract | （契印）| Namespace ↔ User 成员关系 |
| BlackboardFile | BlackboardFile (unchanged) | File on a CentralHub fornix（粮仓）|
| VaultEntry | VaultEntry (unchanged) | Archived entry in Vault（标本）|
| Memory | MemoryEntry | Append-only memory log per Entity |
| InstanceProviderConfig | InstanceProviderConfig (unchanged) | LLM provider config (internal) |

---

## Design Rules

1. **Slug = unique identifier (DB layer)**. Display = i18n key (UI layer). DB does not store display_name columns.
2. **Backend code uses backend names**. Frontend UI uses display names resolved from i18n.
3. **Decision rule**: If a concept is not in this table, it doesn't exist yet.
4. **CorridorNode dropped** — edges simplified to any two points connecting directly.
5. **11 神职 → 5 常驻始祖** — 6 个工具/咨询型角色（唤灵/灵视/衡判/游魂/潜知/百瞳）降级为 subagent 能力（v5.1）；旧 11 拼音 slug 仅 5 个映射到动物 slug（mi-shi→fox / an-xing→beaver / an-ying→sparrow / zhu-jin→coyote / jiu-ri→lion），其余退出命名体系。
6. **Learning 动作** — Instance→Entity = 蜕变（promotion）；Entity→BaseClass = 演化（transmutation）；Memory→capability = 领悟（distill）。
7. **代码名/DB/API 不动** — v5 只改 UI 显示名与 5 个动物 slug；后端代码名（Organization/Namespace/Workspace/BaseClass/Entity/Instance 等）不变。

---

*v5 映射表 2026-08-07。15d 快照归档于 `docs/archive/metaphor-name-table-15d.md`；决策 SoT `.omo/evidence/v5-rename-decisions.md`；执行总图 `.omo/plans/v5-roadmap.md`。*
