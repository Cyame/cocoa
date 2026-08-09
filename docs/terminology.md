> **Canonical source**: v5 命名基线（2026-08-07 终稿）。决策 SoT：`.omo/evidence/v5-rename-decisions.md`。
> **Prior**: 15d（克苏鲁）命名已归档至 `docs/archive/terminology-15d.md`（只读）。
> **执行波**: v5（`.omo/plans/v5-roadmap.md`）——v5.0 命名波起 UI 显示名逐步切换；后端代码名/DB/API 不动。

One-line definitions for every Cocoa code-term (backend), display-name (frontend 山海+生物世界观), and protocol entity. Code-terms stay English; display-names in parentheses are for product UI reference.

---

## Structure Terms（3 层租户 + 3 层实体）

### 租户层级（大陆 → 区域 → 生境）

- **Organization**（大陆）— Top-level isolation unit. 单租户默认 slug=`default`。
- **Namespace**（区域）— Within an Organization: **region partition**（e.g. coding vs social-media），**not** env。Entity（血脉）belongs here so region identity spans multiple Workspaces。
- **Workspace**（生境）— Within a Namespace: a concrete workstream（e.g. a product system or a publish platform）。**代码名保持 `Office` 不变**（v5 只改 UI 显示名，代码名不动）。单租户默认：一个生境 shared by all users。Starts empty。
- **场景意象**（迁徙路线）— Portal 拓扑背景意象；动物通用。

### 实体层级（始祖 → 血脉 → 后裔）

> v5 三层名：从大到小 始祖（源头）> 血脉（传承线）> 后裔（个体）。

- **BaseClass**（始祖）— Preset template defining rules, prompt, commands, tools, provider config, subagent 策略。Created by humans or distilled（演化）from Entity experience。System-scoped。**5 built-in 始祖**（§BaseClasses）。
- **Entity**（血脉）— Instantiation of a BaseClass **per-Namespace**，with identity + accumulated Memory（记忆）。Region-scoped so one Entity can 创生 Instances across Workspaces in that Namespace。Can be promoted（蜕变）/transmuted（演化）。
- **Instance**（后裔）— Running materialization of an Entity in one Workspace。One Instance per pod。Lifecycle ≤ Workspace。**Invariant**: at most one active Instance per `(workspace_id, entity_id)` because `@slug` addresses the Entity。
- **Membership**（智人 / 生物）— Workspace presence with posx/posy。Exclusive-FK: user XOR instance。**v5 产品名**: user row = **智人**（真人，对应 15d 觉醒者）; instance row = **生物**（AI 成员，对应 15d 迷失者）。
- **NamespaceContract**（成员）— Namespace ↔ User 关系。**v5 不再造专有名词**：直接表达为「某区域的成员」。

### 结构概念

- **Passage**（兽道）— Adjacency edge between two Memberships, defining the selectable neighbor set for messaging。CorridorNode dropped。
- **CentralHub**（信号塔）— Per-Workspace 协作中枢容器，含 4 脑区（Fornix 粮仓 / 额叶 / 脑干 / **小脑 = 内置中央智能体 CerebellumAgent 1:1**）。Display 中文「信号塔」，backend 代码名 `CentralHub`。
- **CerebellumAgent**（小脑 / 中央智能体）— Built-in system agent on every CentralHub。v4: migrates to Entity(`is_cerebellum`) + Instance。
- **Fornix**（粮仓）— Active shared file region per CentralHub（对应 15d 穹窿）。Display 中文「粮仓」。
- **Vault**（标本）— Cold archive per Workspace。DB KV (`vault_entries`, optional inline value); eventual MinIO/S3 via `archived_key`。Display 中文「标本」。
- **Memory**（记忆）— Append-only per-Entity memory log, indexed by kind (experience/lesson/decision/problem) and time。No `updated_at` column。
- **Event**（足迹）— Audit log row。Display 中文「足迹」（对应 15d 印痕）。
- **DeployRecord**（诞生记录）— K8s deployment lifecycle record: 9-step pipeline。Display 中文「诞生记录」（对应 15d 降世记录）。
- **Topology**（领地地图）— Spatial visualization of Workspace members as SVG nodes with glow halos, 3 interaction modes (Select/Connect/Move), message-flow particle animation。Display 中文「领地地图」（对应 15d 心灵图景）。
- **SystemHub**（星球中枢）- Org-level implicit assistant for description generation and LLM defaults。Backend 代码名 `system_hub`。Display 中文「星球中枢」（v5.0.1 从「系统中枢」改名）。
- **IntelligenceProvider**（智能）- LLM provider configured at org level。Backend 代码名 `OrganizationProvider`。Display 中文「智能」（v5.0.1 从「智能供者」改名）。
- **AiGene**（生物基因）- Capability pack (tool/skill/command) installable on bloodlines。Display 中文「生物基因」（v5.0.1 从「深海基因」改名；对齐 AI 成员=生物）。
- **UserGene**（智人基因）- Permission/capability gene for human users。Display 中文「智人基因」（对齐真人=智人）。
- **summon / spawn**（创生）- 动词：创建血脉（Entity）或后裔（Instance）。v5.0.1 从「召唤」改名，与名词体系对齐。

### Runtime 概念

- **Workspace control plane** — Cocoa's operator + harness surface (Portal, Supervisor, Boulder, Passage, CentralHub, deploy, observability)。Product peer: a more flexible / observable **senpi · oh-my-openagent · oh-my-pi**。Not the per-Instance agent binary。
- **pi runtime** — Preferred sandboxed agent loop that drives each **Instance（后裔）**。Entity `system_prompt` + `config_override` serialize to pi AgentConfig。React runtime is an optional alternative。**Not** Senpi CLI。
- **LoopState**（心智状态）— Harness runtime state for an Instance: loop_status (6 states), continuation_count, breaker_config, last_checkpoint_at。保留中性词。
- **InstanceProviderConfig** — LLM provider configuration for an Instance。Internal config, no UI equivalent。
- **delivery_mode**（投递模式, v4.7）— How a collaboration/inject payload reaches an Instance: `notify` / `soft_inject` / `wake`。
- **subagent 能力** — Runtime 内部机制（pi task tool / opencode 子代理 / Claude Task），由 Host adapter 映射为「模块功能」；**不进拓扑、不进 Tunnel 协议、不进 Memory/蒸馏链**。6 个内置 subagent 能力：唤灵/灵视/衡判/游魂/潜知/百瞳（对应 15d 神职降级，v5.1 落实）。

---

## BaseClasses（5 Built-in 始祖）

> v5 终稿：11 神职 → **5 常驻始祖**（有动物名）。其余 6 神职（唤灵/灵视/衡判/游魂/潜知/百瞳）**降级为 subagent 能力**，不命名、不占拓扑（v5.1 落实）。Slug = 英文动物名 kebab-case。Display = i18n key。DB does not store display_name column。

| # | Slug | Display | 15d 名 | Role | omo Agent Source |
|---|---|---|---|---|---|
| 1 | `fox` | 狐狸 | 密士 | Interview planner, plan mode sticky, `.omo` plan writer | Prometheus (Strategic Planner) |
| 2 | `beaver` | 海狸 | 暗行 | Solo full-stack coder, boulder-pusher | Sisyphus (Main Coder) |
| 3 | `sparrow` | 麻雀 | 暗影 | Junior coder, high-throughput fast response | Sisyphus-Junior |
| 4 | `coyote` | 郊狼 | 铸金 | Autonomous deep worker, goal-driven | Hephaestus |
| 5 | `lion` | 狮子 | 旧日 | Top-level delegation / monitoring / approval | Atlas (Orchestrator) |

### 内置 subagent 能力（v5.1 落实，不命名）

> T1 已建 6 个能力 agent：`cocoa-instance-host/subagents/agents/{intent,architecture,quality,explore,research,vision}.md`；frontmatter `name` = 能力 id，`subagent_strategy.enabled` 值复用同名。

| 能力 id | 15d 神职 | 能力角色 | omo Agent Source | 归属（per-始祖声明） |
|---|---|---|---|---|
| `intent` | 唤灵 | Intent analysis, pre-planner | Metis | 常驻始祖按需声明 |
| `architecture` | 灵视 | Read-only architecture / hard debugging | Oracle | 常驻始祖按需声明 |
| `quality` | 衡判 | Quality gate: review/approve/reject | Momus | 常驻始祖按需声明 |
| `explore` | 游魂 | Codebase grep / exploration | Explore | 常驻始祖按需声明 |
| `research` | 潜知 | External reference + multi-repo + docs | Librarian | 常驻始祖按需声明 |
| `vision` | 百瞳 | Visual / media / audio analysis | Multimodal-Looker | 常驻始祖按需声明 |

---

## Learning 动作（领悟 / 蜕变 / 演化）

| 后端动作 | 15d 名 | v5 名 | 语义 |
|---|---|---|---|
| distill | 蒸馏 | **领悟** | Memory（记忆）→ capability；P10「学习」页面同步改「领悟」 |
| promote | 晋升 | **蜕变** | Instance（后裔）→ Entity（血脉）：运行状态 + Memory 回写，就地增强 |
| transmute | 炼化 | **演化** | Entity（血脉）→ BaseClass（始祖）：经验蒸馏成新始祖，新 slug 全域可用 |

---

## Sub-entities（Data Layer）

Code-term-only entities from the core domain model. No product UI display-names.

- **User** — Human authentication identity: username, email, password hash。
- **BaseClass**（was EmployeePreset）— Persisted preset record storing slug, manifest JSONB, version。
- **Entity**（was Employee）— Per-Namespace identity referencing a BaseClass, with accumulated memory across Workspaces。
- **Membership**（智人 / 生物）— Workspace presence。Exclusive-FK user XOR instance。
- **NamespaceContract**（成员）— Namespace-scoped human membership（v5 概念化）。
- **BlackboardFile** / **FornixFile** — File record on CentralHub fornix（粮仓）。
- **CerebellumAgent** — Built-in central agent (1:1 CentralHub); system-owned, not a Membership。
- **VaultEntry**（标本条目）— Archived KV entry in a Vault。
- **Memory**（was MemoryEntry）— Append-only memory log entry per Entity, indexed by kind and time。
- **InstanceProviderConfig** — LLM provider config for an Instance。

---

## Concepts

- **Entity-as-role-identity** — Entity（血脉）is a persistent role identity composed of a BaseClass（始祖）manifest plus shared cross-instance Memory; it grows as memory accumulates。
- **Instance=materialization** — An Instance（后裔）is a concrete materialization of an Entity in one Workspace, with isolated workspace and runtime。
- **near-neighbor messaging** — Messaging restricted to passage（兽道）-defined adjacent nodes only; no broadcast fan-out。
- **activation trigger** — Event that causes a node to sync topology and state: daily-report self-sync, on-mention, or scheduled task invocation。
- **slash-protocol** — Structured turn-based command grammar: a Turn is a list of Directives, each with optional target, command, args, and content-ref。
- **directive** — A single command unit within a Turn: target_entity, cmd, args, content_ref, and raw_text。
- **command-registry** — Registry of four command families: GLOBAL (/read, /list, /write, /archive), PER-PRESET (manifest.commands), CONTROL (/interrupt, /pause, /resume, /status, /snapshot), LEARNING (/distill, /consolidate, /reflect)。
- **content-ref** — A scope-qualified reference to content: mandatory scope prefix (workspace|blackboard|vault|memory) with optional path。
- **composer compartmentalization** — The Composer UI splits a message into per-entity compartments before send。
- **subagent 策略** — Per-始祖 manifest 声明：能否使用 subagent、模板、约束（v5.1 落实）。

---

*v5 命名基线 2026-08-07。15d 快照归档于 `docs/archive/terminology-15d.md`；决策 SoT `.omo/evidence/v5-rename-decisions.md`；执行总图 `.omo/plans/v5-roadmap.md`。*
