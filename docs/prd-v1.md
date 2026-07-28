# Cocoa PRD v1 — 交互设计文档

> **Status**: 写作中 (15e PRD wave)
> **Scope**: 全部 10 个 portal 页面 + 首次运行引导 + 蒸馏 UI 的交互规格
> **基线**: `.omo/drafts/phase-15d-product-spec.md` + `phase-15d-naming-system.md`（36 项决策已锁）+ `docs/terminology.md` + `docs/metaphor-name-table.md`
> **代码 rename**: pending 15d-rename wave — UI 文案与后端 API 路径暂不同步

---

## §1 产品概述

### 定位
**多智能体控制台**——单一 Workspace 中，**真人操作员**（旁观者 / 觉醒者权限）召唤、观察、调度 AI 化身（Instance）。Workspace 共享神职（BaseClass）池、共享主脑（CentralHub）状态、共享通道（Passage）连接拓扑。

> **核心身份区分**：Cocoa 中只有**真人用户**（通过觉醒基因管理权限位）——见 §2.2.2。所有"神职"（BaseClass）、"眷族"（Entity）、"化身"（Instance）都是 **AI 智能体**——它们由真人召唤、配置、调度，但不与真人平级。"浅识者"和"深潜者"是 AI 智能体的两种运行形态，不是真人角色。

### 与传统 chat 工具的核心差异
| 维度 | 传统 chat | Cocoa |
|---|---|---|
| 化身存在 | 一次性回复，关闭即结束 | 持续 loop + Memory + 共享主脑，不结束 |
| 状态可见 | 用户看不见化身内部 | 化身 loop_status 通过 glow 颜色实时反映 |
| 多人协作 | 一对一对话 | 多个真人 + 多个 AI 化身共享 Workspace、跨化身派活 |
| 记忆 | 仅当前会话上下文 | AI 跨化身追加 Memory（晋升 / 炼化复用）|
| 拓扑 | 平面会话列表 | SVG 心灵图景，节点 + 通道 + 3 模式 |

### Workspace 默认状态
**单租户**：1 Organization + 1 Namespace + 1 Workspace，**空启动**。所有真人共享这一个 Workspace。无自动预载神职眷族。真人首次进入看到的应当是召唤第一位 AI 眷族的引导 CTA，不是空列表。

### 关键技术约束（影响 UX）
- 神职 slug 是 DB 唯一标识；UI label 走 i18n JSON
- AI 化身只有一个来源：先创建眷族（Entity），再 spawn 化身（Instance）
- 蒸馏 2 动作：晋升（Instance 经验 → Entity 原地增强）、炼化（Entity 经验 → BaseClass 跨 Workspace 复用）
- 拓扑无 CorridorNode 概念——任意两点直连

---

## §2 三层正交概念：职阶 / 能力 / 知识

> **关键约束**：本节 3 个概念**完全正交**：
> - **职阶（Lab Ranks）** — 一个生物（真人 / AI）有且只有的 1 个分类，互斥（详见 §2.1）
> - **能力系统（Capabilities）** — "能做什么"，AI 与人类双侧都存在，**多选**
> - **知识系统（Knowledge）** — 仅对 **Instance** 有效（AI 化身层），与职阶 / 能力完全独立
>
> **核心抽象：基因（Gene）** — 共有两类，"基因 = 一组命名打包"是统一的，但结构完全不同：
> - **觉醒基因**（人类侧）：权限组合，用于能力位管理
> - **深海基因**（AI 侧）：capability 打包，对应 nodeskclaw 的 `gene_service.py` 4 类形态（tool-gene / meta-gene / genome / workflow-gene）
>
> 描述上必须严格区分。详见 §2.2 双侧对照。

### §2.1 职阶体系（Lab Ranks）— 互斥

> **核心约束**：Cocoa 的 Lab Ranks 是一个"分类体系"——每个"生物"（无论是真人用户还是 AI 智能体）**有且只有 1 个职阶**，是互斥分类，**不是可切换的模式**。
>
> - 真人用户：1 个职阶 = **觉醒者**
> - AI 智能体（Entity / Instance）：1 个职阶 = **浅识者** 或 **深潜者** 二选一
>
> 觉醒者与浅识 / 深潜者**不互通**——觉醒者专属于真人；浅识 / 深潜专属于 AI。这 3 个名字字面上像"深浅连续"，但**实际是 3 个独立的范畴**（人类范畴 vs AI 形态范畴）。
>
> **重要**：职阶不描述"我现在在做什么"——它只是分类。人在系统里不需要"切换职阶"——你就是你（觉醒者），不会变成别的。具体操作靠**能力位**（§2.2）和**基因预设**（觉醒基因 / 深海基因 / 浅识基因）来区分。

#### 三个职阶定义

| 职阶 | 范畴 | 含义 |
|---|---|---|
| **觉醒者**（director） | 真人 User.role | 真人操作员，已醒可指挥。**仅适用于真人用户**，不会分配给 AI 智能体。 |
| **深潜者**（researcher） | AI Instance rank | AI 智能体的持久化形态 + Memory 跨化身复用，越潜越深 |
| **浅识者**（intern） | AI Instance rank | AI 智能体的无状态形态，无 Memory，每次新启动 |

#### 互斥性约束
- 1 个真人 User 永远职阶 = 觉醒者（不变，不可切换）
- 1 个 AI 智能体 (Entity) 职阶 = 浅识 OR 深潜（二选一），**Entity 创建时定，创建后冻结不可改**。所有从同一 Entity 派生的 Instance rank 必须一致——保证行为一致性
- AI 与真人**不互通**：不能把"觉醒者"分配给 AI，也不能给真人标"深潜者"
- **唯一可调整 rank 时机**：Entity 从 BaseClass 派生时（创建瞬间）。用户可基于 BaseClass 默认值**覆盖一次**，之后冻结
- **蒸馏动作不改 rank**：晋升 (Instance → Entity) 与炼化 (Entity → BaseClass) 都是 Memory / 经验层的动作，跟 rank 维度正交。晋升**不会**把浅识者升到深潜者

> **命名渊源**：3 个 Lab Ranks 名字都源自 Cthulhu 神秘系"觉醒/深潜/浅识"意象，命名顺承 P1 的 6 preset 系统演化为 11 神职 + 3 ranks。命名巧合不等于等价。

---

### §2.2 能力系统 — 双侧各自一套，结构完全不同

> **核心约束**：本节是 §2 中**结构最复杂**的一段。两个 "能力" 概念必须严格区分：
> - **AI 智能体的能力** = 可调用的工具/技能/MCP/LSP。**打包单位 = 深海基因**（plugin / extension 性质，参考 nodeskclaw `gene_service.py`）
> - **真人的能力** = 可执行的操作权限位。**打包单位 = 觉醒基因**（权限组 / 角色牌）
> - 两者**不要混用**。深度参看 nodeskclaw：`/Users/xuwenrui/Documents/Codes/Researches/nodeskclaw/nodeskclaw-backend/app/data/gene_templates/` —— 深海基因有 skill content + tool_allow + scripts + runtime_config 多个字段，比觉醒基因（FK + 字段列表）复杂得多。
>
> **Schema 设计**：使用**两张不同的表**——结构差异大，硬塞同一张表会污染 schema。
> - `human_genes` 表：FK + capability 字段列表（简单）
> - `ai_genes` 表：完整 manifest（skill content + tool allowlist + scripts + runtime config，覆盖 nodeskclaw 4 类基因形态：tool 基因 / 元基因 / 基因组 / 工作流基因 — 见 §2.2.4）

#### §2.2.1 双侧快速对照

| 维度 | AI 智能体侧（Instance 维度） | 真人侧（User 维度） |
|---|---|---|
| 能力原子 | `Capability` 条目（type + name + config） | `Permission` 位（`can_*` 字符串） |
| 能力单一类型 | 1 个 `CapabilityType` 枚举 `skill / tool / mcp / lsp` | 1 个 `Permission` 字典（key → bool） |
| 打包机制 | **深海基因**（plugin-like，多字段 manifest） | **觉醒基因**（权限组，多 key 列表） |
| 打包存储 | `ai_genes` 表（含 skill content / tool allowlist / scripts / runtime_config） | `human_genes` 表（FK + 能力位 list） |
| 注入时机 | 在 Instance **deploy 时**注入（安装到运行时容器） | 在 User 加入 Workspace 时赋予基因预设 |
| 实例化 | Capability 列表被 runtime adapter 部署到容器（skill 写到 skill 目录、tool 注册到 LLM、mcp 启动进程、lsp 客户端启动） | 权限位列表 + 当前 `is_super_admin` bit 进行 OR 求和 |
| 变更高成本 | 高（修改深海基因通常需要 spawn 新 Instance） | 低（修改觉醒基因立即生效，无需重启） |

---

#### §2.2.2 真人侧 — 觉醒基因（Human Gene = Permission Group）

**觉醒基因** = 一组 `can_*` 权限位的命名打包。功能上等价于 nodeskclaw 早期计划的 "role-pack" / "permission-set"。

##### 觉醒基因预设清单（v0 候选）

| 预设名 | 含能力位（示例） | 用途 |
|---|---|---|
| `operator-gene`（默认） | `can_summon_entity`, `can_interrupt_instance`, `can_spawn_instance`, `can_edit_blackboard`, `can_view_audit_log` | 日常 Workspace 操作 |
| `auditor-gene` | `can_view_audit_log`, `can_export_audit_log`, `can_view_all_workspaces` | Audit Mode 自动激活 |
| `admin-gene`（15d 仅 1 个） | 全部能力位 + `can_create_workspace` + `can_delete_workspace` | 首位注册用户自动获得 |
| `viewer-gene`（P16d 后） | `can_view_workspace` + `can_view_topology` + `can_view_audit_log` | 未来 P16d 给只读用户使用（P15d 不实现） |

##### 数据库设计（`human_genes` 表）

```python
class HumanGene(BaseModel):
    # 标准字段
    id, slug, name, description, deleted_at, created_at, updated_at
    
    # 核心字段
    kind: enum("builtin", "custom")           # 内置 4 个 / 自定义
    permission_keys: list[str]                # can_* 字符串列表
    tags: list[str]                            # 可选标记
```

**觉醒基因特性**：
- 一行存一个基因预设
- `permission_keys` 是 `can_*` 字符串列表（FK 到 capability registry 表）
- 内置 4 个（builtin），不可删除，可复制后修改
- 自定义基因可以创建 / 编辑 / 删除

##### 能力位参考表（v0 候选）

| Key | 描述 | 默认归属基因 |
|---|---|---|
| `can_summon_entity` | 召唤眷族 | operator |
| `can_spawn_instance` | spawn 化身 | operator |
| `can_interrupt_instance` | 中断化身 | operator |
| `can_pause_instance` | 暂停化身 | operator |
| `can_edit_central_hub` | 编辑主脑 | operator |
| `can_view_workspace` | 查看 workspace | operator / viewer / auditor |
| `can_view_topology` | 查看心灵图景 | operator / viewer / auditor |
| `can_view_audit_log` | 查看调试印痕 | operator / auditor |
| `can_export_audit_log` | 导出印痕 JSON | auditor |
| `can_manage_genes` | 管理基因预设 | admin |
| `can_create_workspace` | 创建 workspace | admin |
| `can_delete_workspace` | 删除 workspace | admin |

---

#### §2.2.3 AI 智能体侧 — 深海基因（AI Gene = Capability Plugin / Extension）

> **名称说明**：此处的 "深海基因" 是 AI 智能体的能力打包单位，对应 nodeskclaw 现有的 4 类基因形态（tool 基因 / meta-gene 元基因 / genome 基因组 / workflow-gene 工作流基因），用于在深海智能体范围内复用与组合。
>
> AI 智能体的"intern / researcher" 两种 rank **不再**与不同基因类型绑定——rank 描述的是"AI 智能体在生命周期的形态（无状态 vs 持久化）"，与它装什么基因无关。Intern 与 Researcher 共用同一套深海基因机制。

##### 深海基因 4 类形态（对应 nodeskclaw templates 分类）

| 类别 | 名称 | 用途 | nodeskclaw 例子 |
|---|---|---|---|
| 工具基因 | `tool-gene` | 单个 tool / mcp / lsp / skill 容器化 | `nodeskclaw-blackboard-tools.json` |
| 元基因 | `meta-gene` | 跨工具的横切关注（路由、模式、协作规约） | `meta_gene_tool_routing.json`、`meta_gene_plan_mode.json` |
| 基因组 | `genome` | 多基因捆绑打包（含 tool-gene + meta-gene） | `genome_ai_employee_basics.json` |
| 工作流基因 | `workflow-gene` | 多步骤流水线（含阶段编排 + 推荐拓扑） | `workflow_genome_example.json` |

##### 数据库设计（`ai_genes` 表）

```python
class AiGene(BaseModel):
    # 标准字段
    id, slug, name, description, deleted_at, created_at, updated_at
    
    # 分类
    kind: enum("tool-gene", "meta-gene", "genome", "workflow-gene")
    tags: list[str]
    
    # Manifest（节点兼容 nodeskclaw 字段）
    manifest: dict = {
        "skill": {                              # 可选：skill content
            "name": "...",
            "content": "---\nname: ..."
        },
        "tool_allow": [                         # 可选：tool 白名单
            "nodeskclaw_bpilot",
            "group:fs"
        ],
        "scripts": {                            # 可选：Python CLI 脚本
            "filename.py": "..."
        },
        "runtime_config": {                     # 可选：运行时配置补丁
            "PROXY_URL": "...",
            "MAX_TOKENS": 4096
        }
    }
    
    # 基因组特有
    gene_slugs: list[str]                       # 仅 genome 类使用，引用其他基因
    
    # 通用
    config_override: dict                       # 模板覆盖配置
```

**为什么是单独的表？**

1. **schema 完全不像**：觉醒基因只有 FK + permission_keys 列表；深海基因有 manifest 4 字段 + gene_slugs + config_override + scripts 实际代码内容。
2. **存储空间不同**：觉醒基因几行；深海基因的 `scripts` 字段可能含真实 Python 脚本内容（KB 级别）。
3. **生命周期不同**：觉醒基因一旦绑定立即生效；深海基因需要 deploy 流程（安装到 Instance 容器，运行时才能用）。
4. **模板来源不同**：觉醒基因是 Cocoa 内置；深海基因将来可能会从 GeneHub 之类的外部基因市场同步（与 nodeskclaw SEED_GENES 流程一致）。
5. **跨表用 FK 引用**：Entity 创建时可指定深海基因（深海基因与 BaseClass 是 N:N 关系）。一个深海基因可以被多个 BaseClass 引用，一个 BaseClass 也会引用多个深海基因。

##### 能力原子（`Capability`）

```ts
type CapabilityType = 'skill' | 'tool' | 'mcp' | 'lsp';

interface Capability {
  type: CapabilityType;            // 4 选 1
  name: string;                    // 'fetch_url' (tool) / 'search_code' (skill) / 'github-mcp' (mcp) / 'ts-lsp' (lsp)
  scope?: 'global' | 'workspace' | 'entity';
  config?: Record<string, unknown>;
}
```

- **skill**：领域知识 / 提示词模版 / 推理技巧（"代码 review checklist"）
- **tool**：可调用工具（shell, fetch_url, write_file...）
- **mcp**：Model Context Protocol 服务（外部进程）
- **lsp**：Language Server Protocol 客户端（代码智能）

具体 capability 集合由 BaseClass manifest 的 `capabilities` 字段在 spawn 时复制到 Instance。

##### 深海基因的安装流程（参考 nodeskclaw `GeneInstallAdapter`）

1. 用户在 BaseClass 编辑界面勾选需要的深海基因
2. 创建 Entity 时从 BaseClass 复制深海基因列表到 Entity
3. spawn Instance 时按照 Entity 的深海基因列表：
   - 写入 `Instance.runtime_config.installed_genes`
   - runtime adapter（GeneInstallAdapter）逐个把深海基因的 manifest 部署到 Instance 容器：
     - skill → 写到 skill 目录
     - tool → 注册到 LLM tool 列表
     - mcp → 启动 MCP 服务进程
     - script → 写入容器文件系统并 chmod +x
     - runtime_config → 浅合并到 openclaw.json
4. 安装完成生成 `EventLog` 印痕（`installed_genes.{slug}`）

---

#### §2.2.4 关键交互约束

- **觉醒基因 变更**：立即生效（改 `permission_keys` → 用户下次鉴权即生效）。产生 `EventLog` 印痕。
- **深海基因 变更**：高成本，**新 Instance 才生效**。已运行的 Instance 不受影响；想让它生效需要重启 / 重新 deploy。
- **跨 Workspace 复用**：两种基因都支持跨 Workspace 复用（深海基因因为是 plugin，是 reusable 性质；觉醒基因因为是角色预设，也是 reusable 性质）。
- **管理员能力**：超管（首位注册用户的 admin-gene 持有者）可以创建自定义基因，但内置 4 个基因（operator / auditor / admin / viewer）不可删除，可被复制。

---

#### §2.2.5 命名隔离警告（重要）

- **觉醒基因** = 真人权限组合（人类侧）— 简单 FK + 字符串列表
- **深海基因** = AI capability 打包（AI 侧）— manifest 多字段、可能含 scripts 代码
- 二者**共享 "基因" 词是因为都是命名打包**，但实质完全不同：
  - 觉醒基因 = "谁能做什么"（权限位组合）
  - 深海基因 = "AI 能调用什么"（capability 组合）
- **严禁混用**：觉醒基因不能包含 AI capability；深海基因不能含人类权限位。
- 蒸馏动作（晋升 / 炼化）是**另一个维度**的概念——是关于 AI 经验积累 / 输出新神职的，跟基因（打包）正交。蒸馏产物（新 BaseClass）可以引用深海基因作为默认安装包。

---

### §2.3 知识系统（Knowledge）— 仅 Instance 有效

**关键约束**：知识系统与职阶、能力**完全解耦**，且**只对 AI Instance 有效**——对 Entity / BaseClass / 真人 都没有意义（真人不需要"知识注入"，Entity 是身份标识、BaseClass 是模板）。

#### 范围
- ✅ 仅 `Instance.runtime_config.knowledge` 字段
- ❌ 不存在于 Entity / BaseClass / User / Membership

#### 当前实际形态（v0）

知识系统的"v0"实现非常朴素：**通过环境变量 + 文件注入**到 Instance 容器。这与 nodeskclaw 当前的做法一致。

| 形态 | 注入方式 | 用途 |
|---|---|---|
| `env` | 写入 Instance 容器环境变量（如 `KNOWLEDGE_DOCS_PATH=/workspace/docs`） | 给 LLM context 注入私有知识库路径 |
| `file` | 把文件挂载到 Instance 容器（PVC 或 configmap） | 注入文档 / schema / 参考资料 |

**v0 操作界面**（简化）：
- 化身详情页 → "知识" tab → 列出当前已注入的 env / file
- 「+ 添加 env」按钮 → 输入 key=value → POST Instance runtime config
- 「+ 上传文件」按钮 → 选择文件 → 上传到 PVC → 关联到 Instance
- 「移除」按钮 → 解除关联
- 修改瞬时生效（无需重启 Instance，**破除 v0 与未来版本的一致约束**—— v0 通过环境变量 / 文件挂载，运行时变更）

#### 未来扩展（暂不计划）
- RAG / 向量数据库（KB 检索）
- 多模态知识（图谱 / 视频帧）
- 知识继承（Entity 层的共享知识库）

> **重要**：以上扩展**不在当前 roadmap 中**，等 P16d 后再评估。如果有人来问"知识能不能做 RAG"——告诉他们在 `docs/prd-v1.md` §2.3 显式说不计划。

---

## §3 命名对照表

### 3.1 Backend → Frontend 映射

引用 `docs/metaphor-name-table.md` 的完整映射表。这里只列最常用的 8 个：

| Backend (code/DB) | Frontend Display | 用途 |
|---|---|---|
| `Workspace` | 空间 | 协作容器（原 Office） |
| `BaseClass` | 神职 | 预设模板（原 EmployeePreset） |
| `Entity` | 眷族 | 身份实例（原 Employee） |
| `Instance` | 化身 | 运行时 pod |
| `Membership` | 契印 | Workspace 成员关系 |
| `Passage` | 通道 | 拓扑边（原 Corridor，CorridorNode 已 drop） |
| `CentralHub` | 主脑 | 协作中枢容器（4 脑区合成） |
| `Memory` | 记忆沉淀 | 追加日志（原 MemoryEntry） |

### 3.2 11 神职表

| Slug | Display | 职能 | Command surface |
|---|---|---|---|
| `mi-shi` | 密士 | 战略规划、计划模式 | /plan /decompose /prioritize |
| `huan-ling` | 唤灵 | 意图分析、预规划 | /analyze /clarify /propose |
| `an-xing` | 暗行 | 单兵全栈推任务 | /plan /execute /build /test |
| `an-ying` | 暗影 | Junior 廉价快速 | /execute /build /test |
| `zhu-jin` | 铸金 | 目标驱动工人 | /execute /build /test |
| `ling-shi` | 灵视 | 只读架构 / 调试 | /analyze /predict /review |
| `heng-pan` | 衡判 | 质量门禁 | /review /approve /reject |
| `you-hun` | 游魂 | 仓内 grep / 探索 | /search /survey /report |
| `qian-zhi` | 潜知 | 外部引用 / 多仓调研 | /search /reference /survey |
| `bai-tong` | 百瞳 | 视觉 / 媒体 / 音频 | /look /analyze /describe |
| `jiu-ri` | 旧日 | 顶层委派 / 监控 | /delegate /monitor /approve |

### 3.3 Lab Ranks

| Backend | Display | 范畴 | 含义 |
|---|---|---|---|
| `intern` | 浅识者 | AI Instance rank | 无状态热加载，无 Memory，每次新启动；刚窥见一丝真理 |
| `researcher` | 深潜者 | AI Instance rank | 完整神职 + Memory，持久化积累经验；越潜越深 |
| `director` | 觉醒者 | Human user role | 真人操作员，已醒可指挥 |

---

## §4 全局 UX 原则

1. **空态优先** — 首次进入看到的是 CTA（创建第一个眷族），不是空白页。空态文案用第二人称"你"而不是"用户"。
2. **错误人话化** — 5xx / 网络错误用 `errors.*` i18n 文案，不暴露后端 stack 或 SQL 异常名。Unknown 错误兜底文案统一。
3. **状态可见** — 化身 loop_status 通过节点 glow 颜色实时反映（running=绿/强、idle=黄/中、failed=红/强、paused=灰/弱 等）。
4. **操作可逆** — 晋升可回滚（再次晋升会基于新 Memory 重新生成），炼化产出新 slug 不覆盖原 BaseClass。删除走软删除，30 天可恢复。
5. **多语言 first** — 所有面向用户文案走 i18n keys（`deities.mi-shi.name` 等），无硬编码中英文。语言切换在切换瞬间生效，无 flash。
6. **键盘可达** — 拓扑模式 V/C/M 切换、Composer `⌘K` 命令面板、调试页 `R` 刷新。焦点可见。
7. **桌面优先** — desktop-first 设计，移动端体验明确 defer。响应式断点 ≥1024px 优先。
8. **可观测** — 所有用户操作产生 `EventLog`（印痕）记录，可通过 `/debug` 页面回放和导出。无静默失败。
9. **键盘不抢焦点** — 全局快捷键不抢文本输入框焦点（除非显式声明的快捷键如 `⌘K`）。

---

## §6 首次运行引导 + 神职卡片组

### 6.1 触发条件

首次进入 Workspace 时触发：
- 用户从未创建过任何 Entity（眷族）→ Workspace 是空的
- 也即：新注册用户、Workspace 重置、单租户默认空启动的所有场景

### 6.2 引导流程（3 步 modal）

**Modal 行为**：
- 不可关闭（用户必须走完全部 3 步或显式"稍后"）
- 右上角步骤指示器 `1 / 3`、`2 / 3`、`3 / 3`
- 桌面 ≥768px 居中 modal，移动端全屏 sheet

#### Step 1：挑神职
- **标题**："召唤你的第一位眷族"
- **副标题**：从 11 神职中选 1 个。每个神职定义了一组能力与命令。
- **主体**：11 张神职卡片 grid（3 列 desktop / 2 列 tablet / 1 列 mobile）
- **卡片内容**：
  - 神职 display name（密士 / 唤灵 / ...）+ slug（mi-shi / huan-ling / ...）
  - 一句话职能描述
  - 3 个核心命令（chip 样式，例如 `/plan /execute /build`）
  - 鼠标悬停 tooltip：完整职能说明（最长 3 行）
- **状态**：
  - 默认：未选
  - 选中：蓝色边框 + 顶部 checkbox 勾选 + 卡片轻微抬升（translate-y -2px）
  - 禁用：暗影（an-ying）rank=intern 时禁用 researcher 类高级神职（如果走 rank 模式）
- **操作**：
  - 「下一步」按钮：未选时禁用，选中后 enabled
  - 「稍后再说」链接：跳过整个引导，进入空 Workspace（带 Toast"已跳过引导，空 Workspace"）

#### Step 2：起名 + spawn 化身
- **标题**："为眷族起名"
- **副标题**：眷族会基于你选的神职被创建。命名后可以立即 spawn 一个化身。
- **表单字段**：
  - **眷族显示名**（必填，1-32 字符）
    - placeholder：`例如：奈亚探子、克总助理`
    - 实时去重检查（与 Workspace 内现有 Entity.name 冲突时红框 + 提示）
  - **slug**（自动从显示名生成 kebab-case，可编辑）
    - placeholder：`例如：nai-ya-tan-zi`
    - 校验：必须匹配 `/^[a-z][a-z0-9-]*$/`
  - **AI rank 选择**（2 选 1 radio，AI 智能体生命周期形态）：
    - 浅识者（intern）— AI 智能体的无状态形态，无 Memory，每次重启动
    - 深潜者（researcher）— AI 智能体的持久化形态，累积 Memory 跨化身复用（推荐）
    - *觉醒者（director）是真人概念，与此 rank 选择无关*（详见 §2.1）
    - **重要提示**：rank 一旦选定，**Entity 创建后冻结不可改**。所有从此 Entity 派生的 Instance 必须保持同一 rank 行为一致性。如需更改，需新建 Entity（旧 Entity 通过软删除归档保留其 Memory 与穹窿写入）。
- **预览区**：右侧（desktop）/ 下方（mobile）显示该眷族 spawn 化身后的卡片样式预览
- **状态**：
  - 默认：表单为空，「下一步」禁用
  - 已填：「下一步」enabled
  - 提交中：「下一步」显示 loader + 文字「召唤中...」
  - 错误：表单字段下方红字提示（重名 / slug 不合法 / 权限不足）
- **操作**：
  - 「召唤眷族」按钮：POST 创建 Entity，成功后自动进入 Step 3
  - 「上一步」按钮：回到 Step 1

#### Step 3：打招呼
- **标题**："和你的眷族打个招呼"
- **副标题**：这是你第一次和眷族互动。发一条消息让 TA 回应。
- **主体**：
  - 自动填充 Composer（不可编辑）：`@<slug> 你好，认识一下。`
  - 「发送」按钮 + 实时显示化身回复
- **状态**：
  - 发送中：「发送」loader，回复区域显示打字点动画
  - 已回复：完整显示化身的首次回应
  - 错误：化身暂时没回应（retry 按钮 + 5s 后自动 retry 一次）
- **操作**：
  - 「再发一条」按钮：清空 Composer 重新输入
  - 「完成」按钮：关闭 modal，导航到 Workspace 详情页 `/workspaces/:id`

### 6.3 神职卡片组 UX 细节

#### 卡片组件规格
- **尺寸**：桌面 280×320px，平板 240×300px，移动端全宽
- **视觉层次**：
  - 顶部：神职图标（lucide 24px）+ 名称
  - 中部：3 命令 chips（蓝色 / 灰色 / 紫色按命令族）
  - 底部：slug（mono 字体）+ 一句话描述
- **Hover 状态**：
  - 边框颜色变深
  - 抬升 shadow
  - 显示完整职能 tooltip（portal tooltip 组件，500ms delay）

#### 11 神职分组显示
为避免 11 张卡堆在一起视觉嘈杂，按职能分 3 组：

| 组 | 神职 | 视觉标签 |
|---|---|---|
| **规划类** | 密士、唤灵、旧日 | 蓝色 chip |
| **执行类** | 暗行、暗影、铸金 | 绿色 chip |
| **审视类** | 灵视、衡判、游魂、潜知、百瞳 | 紫色 chip |

#### 排序规则
- 默认按 group 内部字母排序
- 用户可按"command 数"或"display name"排序

### 6.4 错误态与边界

| 场景 | 行为 |
|---|---|
| Step 1 用户选神职但 Step 2 slug 冲突 | 保留 Step 1 选择，回到 Step 2 改 slug |
| 网络错误（提交失败） | 显示 Toast「提交失败，请重试」+ 表单不清空 |
| 用户取消整个引导 | Workspace 仍为空，下次进入 Workspace 时再次显示引导 |
| 用户已经创建过 Entity | 跳过整个引导，直接进入 Workspace 详情页 |

### 6.5 与其他页面关系
- **完成后导航**：Workspace 详情页 `/workspaces/:id`，默认显示"神职"tab
- **跳过引导**：进入空 Workspace，显示空态"还没有眷族，点击召唤第一位"
- **重看引导**：设置菜单"重新走一次引导流程"（未来扩展）

---

## §7 导航结构 + AppShell

### 7.1 整体结构（双栏布局）

AppShell 是已登录用户的统一外壳，包裹所有需要鉴权的页面。**所有 9 个内部入口都挂在 AppShell 下**（Login / Register 不挂）。

```
┌──────────────────────────────────────────────────────┐
│ AppShell                                               │
│ ┌──────────┬─────────────────────────────────────────┐│
│ │          │ Topbar（语言切换 / 用户信息 / 登出）   ││
│ │  Sidebar │ Header（页面标题 / 子标题）             ││
│ │  桌面侧  │ ─────────────────────────────────────── ││
│ │  边栏    │ Content（页面主体）                     ││
│ │          │                                          ││
│ └──────────┴─────────────────────────────────────────┘│
│ Mobile Bottom Tab Bar（替代 sidebar）                  │
└──────────────────────────────────────────────────────┘
```

### 7.2 Sidebar 桌面侧边栏（≥768px）

**位置**：固定左侧，宽度 240px，高度 100vh，深色背景（slate-950）

**结构**（自顶向下）：

| 区域 | 内容 |
|---|---|
| Logo 区 | Cocoa 图标 + "Cocoa" + 副标题"控制台" |
| 主导航区 | 9 个入口（见 7.4） |
| 用户区（底部） | 用户名 + 觉醒基因 chip + Super Admin badge + 登出按钮 |

**当前页高亮规则**：
- 匹配当前路由（包括子路由）：背景变蓝（blue-600），文字变白
- 路由匹配通过 React Router v7 的 NavLink `isActive` 自动判定
- 关联 Workspace 时（需要 office_id 的入口），必须选中一个 Workspace 才能高亮

### 7.3 Mobile Bottom Tab Bar（<768px）

**位置**：固定底部，高度 64px，白色背景

**结构**：5-7 个 Tab 横向均分（按需展开成可滚动）

**优先级排序**（从左到右）：
1. 空间（必须有 workspace_id 才能进入）
2. 拓扑（同上）
3. Composer（同上）
4. 调试（无 workspace 限制）
5. 学习（同上）
6. 成员（同上）

**超过 5 个时**：底部 Tab 仅显示 5 个，其余收到"更多"菜单（右上角 ⋯）

### 7.4 9 个导航入口

按 Workspace 依赖关系分组：

#### A. Workspace 内入口（必须选中 workspace 才能访问）

| # | 入口 | 路由 | 图标 | 启用条件 |
|---|---|---|---|---|
| 1 | 空间详情 | `/workspaces/:id` | `Building2` | 总是启用 |
| 2 | 神职列表 | `/workspaces/:id/entities` | `Users` | 总是启用 |
| 3 | 成员列表 | `/workspaces/:id/members` | `Users` | 总是启用 |
| 4 | 拓扑 | `/workspaces/:id/topology` | `Network` | 总是启用 |
| 5 | Composer | `/workspaces/:id/composer` | `Pencil` | 总是启用 |
| 6 | 学习 | `/workspaces/:id/entities` | `BookOpen` | 总是启用 |

#### B. 全局入口（无 workspace 依赖）

| # | 入口 | 路由 | 图标 | 启用条件 |
|---|---|---|---|---|
| 7 | 空间列表 | `/workspaces` | `Building2` | 总是启用 |
| 8 | 调试 | `/debug` | `Bug` | 总是启用 |
| 9 | 登录 | `/login` | (无) | 仅未登录时显示 |

> **Login 不挂 AppShell**：登录页是独立路由，不进 AppShell 包裹。

### 7.5 Topbar（顶部条）

**位置**：AppShell 主体顶部，高度 40px，白底

**结构**（从左到右）：
- 左侧空（占位）
- 右侧：语言切换按钮 → 用户名 + 觉醒基因 chip + Super Admin badge → 登出按钮

**组件**：
- **语言切换**：`LanguageSwitcher` 组件（zh-CN ⇄ en）
- **用户信息**：头像（占位圆）+ 用户名 + 觉醒基因 chip + Super Admin badge（如适用）
  - 觉醒基因 chip：显示当前基因名（如 `operator-gene`），hover 显示能力位列表
  - Super Admin badge：金色徽章，「超管」字样（仅 `is_super_admin=true` 时显示）
- **登出**：按钮点击 → 清 token → 跳 `/login`

### 7.6 Header（页面标题区）

**位置**：Topbar 下方，高度自适应

**结构**：
- **大标题**：H1，32px，semibold（页面名）
- **副标题**：14px，灰色（页面一句话描述）
- **右侧**：页面级操作按钮（可选，例如空间详情的"召唤眷族"按钮）

**页面 Header 样例**（空间详情）：
```
┌────────────────────────────────────────┐
│ 奈亚探子巢穴                  [+ 召唤眷族] │
│ Workspace 详情 · 5 个神职 · 3 个化身   │
└────────────────────────────────────────┘
```

### 7.7 未授权与未选 Workspace 处理

| 场景 | 行为 |
|---|---|
| 未登录访问受保护路由 | 跳 `/login` |
| 已登录但未选 Workspace，访问 workspace 内路由 | 跳 `/workspaces`（列表），Toast「请先选择 Workspace」 |
| 已登录，Workspace ID 无效（404） | 跳 `/workspaces`，Toast「Workspace 不存在或已删除」 |
| Token 过期（API 返回 401） | 清 token + 跳 `/login`，Toast「会话已过期，请重新登录」 |

### 7.8 错误边界

- AppShell 整体包一个 `ErrorBoundary`
- 任意子组件崩溃 → 显示降级 UI："页面遇到错误，请刷新或返回首页"
- 提供"刷新" + "返回首页"按钮

### 7.9 响应式断点

| 断点 | 范围 | 布局 |
|---|---|---|
| mobile | <768px | 隐藏 sidebar，显示 bottom tab bar |
| tablet | 768-1023px | sidebar 显示（240px 宽），简化 header |
| desktop | ≥1024px | 完整 sidebar（240px），完整 header，content 全宽 |

---

## §8 空间列表 + 空间详情页

### 8.1 空间列表页 `/workspaces`

#### 页面定位
- **入口**：Sidebar "空间列表"、Logo 点击、移动端底部 Tab "空间"
- **场景**：登录后的默认页（无 workspace 选中时）、用户想切换 workspace 时
- **典型 Persona**：全部 3 个（架构师/执行者/审计者都会用）

#### 页面结构

```
┌─────────────────────────────────────────────┐
│ Header                                      │
│   标题："空间"                              │
│   副标题："选择 Workspace 进入神职与化身"   │
├─────────────────────────────────────────────┤
│ Content                                     │
│   - 加载中：居中 spinner                     │
│   - 空态：召唤首位眷族 CTA                  │
│   - 列表：workspace 卡片 grid               │
└─────────────────────────────────────────────┘
```

#### 加载态
- 居中 `LoaderCircle` + 文字"加载空间中"（zh）/ "Loading workspaces"（en）

#### 空态（Workspace 列表为空）

这是单租户模式下用户首次进入的常态。**不显示"创建一个 Workspace"按钮**——因为 15d 单租户默认只有 1 个 Workspace 且已自动存在。

**空态文案**：
- 标题："还没有眷族"
- 副标题："召唤你的第一位眷族，开始与 AI 化身协作"
- 主 CTA 按钮："召唤首位眷族" → 触发首次运行引导（§6）
- 次 CTA 链接："了解神职" → 滚动到底部"神职预览"展示 11 张缩略卡

#### 列表态（卡片 grid）

- **布局**：桌面 3 列、平板 2 列、移动 1 列
- **卡片内容**：
  - 顶部：Workspace 图标（`Building2`）+ slug（mono）
  - 中部：Workspace 显示名（H2）+ 创建时间
  - 底部：3 个统计——眷族数 / 化身数 / 主脑状态
- **点击行为**：进入 `/workspaces/:id` 详情页
- **Hover**：边框颜色变深 + 抬升 shadow + "进入 →"箭头显形

#### 错误态
- 401 → 自动跳 `/login`
- 其他错误：顶部红框错误条 + "重试"按钮

### 8.2 空间详情页 `/workspaces/:id`

#### 页面定位
- **入口**：空间列表卡片点击、首次运行引导完成跳转、Sidebar "空间"图标
- **场景**：Workspace 的"主页"，展示眷族 / 化身 / 主脑三个维度
- **典型 Persona**：全部 3 个

#### 页面结构

```
┌─────────────────────────────────────────────┐
│ Header（页面标题区）                         │
│   标题：Workspace 名称                       │
│   副标题：slug · 创建时间                   │
│   右侧操作：[+ 召唤眷族]（§6 引导）          │
├─────────────────────────────────────────────┤
│ Tab Bar（3 个 tab）                          │
│   [神职] [化身] [主脑]                       │
├─────────────────────────────────────────────┤
│ Tab Content                                  │
│   （根据当前 tab 显示不同内容）              │
└─────────────────────────────────────────────┘
```

#### Header 详情
- 大标题：Workspace 显示名（slug 在上方小字 mono 灰色）
- 副标题："5 个眷族 · 3 个化身 · 主脑活跃"
- 右侧操作按钮（需 `can_summon_entity`）：
  - "+ 召唤眷族"（触发 §6 引导，Workspace 已空时高亮 + 动画）
  - "⋯"菜单（需 `can_edit_workspace`）：编辑 Workspace 名 / 软删除（30 天可恢复）

#### Tab 1：神职（原"成员"）

**含义变更**：15d 后，"成员" = Membership（契印），是 Workspace 内的契约关系；"神职" = Entity（眷族），是 agent 身份。本 tab 显示眷族而非人。

**空态**：
- 图标：`UserRound`
- 标题："还没有眷族"
- 副标题："从 11 神职中召唤你的第一位眷族"
- CTA："召唤眷族" → 触发 §6 引导

**列表态**：
- **布局**：3 列 grid，desktop
- **卡片内容**：
  - 顶部：头像圆（眷族 display name 首字）+ 神职 chip（神职 display name）
  - 中部：眷族显示名（H3）+ slug（mono 小字）
  - 底部：AI rank badge（浅识者 / 深潜者）+ 创建时间
- **点击**：进入 `/entities/:id` 详情页（P10 学习页 §13）
- **右键菜单**（需 `can_summon_entity`）：
  - 软删除（30 天可恢复）
  - 跳到该眷族的 Memory 页

#### Tab 2：化身

**空态**：
- 图标：`Cpu`
- 标题："还没有化身"
- 副标题："眷族存在不代表化身在运行。召唤一位眷族后 spawn 化身"
- CTA："前往眷族列表挑选" → 跳 Tab 1

**列表态**：
- **布局**：垂直列表，每行一个化身
- **每行内容**：
  - 左：化身图标（圆颜色对应 loop_status glow）+ 化身 ID 前 8 位
  - 中：眷族名（链向眷族）+ K8s pod name
  - 右：loop_status badge（running/idle/paused/failed 颜色）
- **点击**：进入 `/workspaces/:id/instances/:iid`（§9 化身详情页）
- **批量操作**（需 `can_interrupt_instance`）：勾选多个 → 批量 interrupt / resume

#### Tab 3：主脑（CentralHub）— 4 脑区协作中枢

> **核心概念**：**主脑 = 4 脑区合成的协作中枢容器**。每个 Workspace 有且只有 1 个 CentralHub（1:1），里面包含 4 个独立功能的子区（脑区），每个脑区对应 1 个独立子表：
>
> | 脑区 | Backend 表名 | Display (zh) | 功能 |
> |---|---|---|---|
> | 穹窿（fornix） | `fornix` | 穹窿 | Workspace 共通工作目录（files / shared assets / attachments）— 现有 BlackboardFile |
> | 额叶（frontal lobe） | `frontal_lobe_kanbans` | 额叶 | Kanban + Todo（继承 oh-my-openagent 的 todo 系统） |
> | 脑干（brainstem） | `brainstem_schedules` | 脑干 | 定时任务 / 延时任务（cron-like 调度，Workspace 作用域） |
> | 小脑（cerebellum） | `cerebellum_agents` | 小脑 | 1 个系统级中央 agent，仅服务主脑，不参与 Workspace 整体编排，承担中央智能功能（状态监控/感知聚合等）|
>
> 数据模型采用**分子表**方案（核心已确定），4 个脑区各自独立表，1 个 CentralHub 表承担容器角色（1:1 per workspace）。

**Tab 3 子结构**：进入 Tab 3 后默认打开"概览"视图 + 4 个脑区子 tab（穹窿 / 额叶 / 脑干 / 小脑）。

##### §8.2.3a CentralHub 概览（默认视图）

**空态**：
- 图标：`Notebook`
- 标题："主脑是空的"
- 副标题："共享状态尚未初始化。让你的化身写第一条主脑内容吧"
- CTA："召唤眷族" → 触发 §6 引导

**填充态（概览视图）**：
- **布局**：顶部统计 + 4 脑区状态卡片 grid（2×2）
- **顶部统计**（4 脑区计数汇总）：
  - 穹窿文件数 · 额叶活跃 todo 数 · 脑干定时任务数 · 小脑 agent 心智状态
- **4 张脑区状态卡片**（每卡 1 脑区）：
  - 卡头：脑区名称 + 中文 display + 当前健康状态 badge（绿/黄/红）
  - 卡体：2-3 个核心 metric（如穹窿显示文件大小 / 修改时间，额叶显示活跃 todo / 已完成 todo，脑干显示下次执行 / 已失败任务，小脑显示 agent loop_status / 续命次数）
  - 卡底：「进入此脑区」按钮（→ Tab 3.x 视图）

##### §8.2.3b 穹窿（fornix）— 工作目录视图

**Tab 切换路径**：`/workspaces/:id?tab=centralHub&area=fornix`

**结构**：
- 顶部面包屑：`Workspace · 主脑 · 穹窿`
- 左侧：BlackboardFile 树状目录（保留现有 P6 BlackboardFile 模型，字段名 `fornix_files` 后续 15d-rename wave 更新）
- 右侧：文件详情预览 + 操作（下载 / 替换 / 删除）
- **继承 P6 操作**：GET/PATCH/POST/DELETE 文件 + 归档到 Vault

##### §8.2.3c 额叶（frontal lobe）— Kanban + Todo

**Tab 切换路径**：`/workspaces/:id?tab=centralHub&area=frontal-lobe`

**结构**：
- 左侧列：Kanban 看板（todo 状态切换列：backlog / in-progress / done / blocked）
- 右侧：当前选中 todo 详情（创建者 / 关联 entity / 关联 instance / 时间线）
- 「+ 新建 todo」按钮（手动 / 由 instance 通过基因自动创建）

**Todo 来源**：
- 真人手动创建
- 化身通过基因（深海基因 install 包含 todo-creation gene）自动写入
- 跨 Workspace 不可见，但 Workspace 内全员可读（权限 后续可细化）

##### §8.2.3d 脑干（brainstem）— 调度任务

**Tab 切换路径**：`/workspaces/:id?tab=centralHub&area=brainstem`

**结构**：
- 任务列表：name + cron/interval + 下次执行时间 + 上次结果 + 状态
- 「+ 新建调度」按钮（弹模态：name / cron expr 或 interval / 目标 / 首次执行时间）
- 操作：暂停 / 启用 / 删除 / 查看执行历史

**继承 oh-my-openagent 的调度概念**（待验证细节再细化）。

##### §8.2.3e 小脑（cerebellum）— 中央 agent

**Tab 切换路径**：`/workspaces/:id?tab=centralHub&area=cerebellum`

**结构**：
- 中央 agent 详情（不是普通 Entity 详情，因为小脑 agent 是系统级而非用户创建）
- 显示内容：神职名 + 心智状态 + 当前任务（脑干调度触发的任务 / 穹窿 / 额叶 触发的感知聚合）
- 操作（仅超管）：
  - 查看小脑 agent 完整 Memory（系统级 schema）
  - 重启小脑 agent（force restart）
  - 修改小脑 agent 的 prompt 配置（受 `can_manage_cerebellum_agent` 限制）

**小脑 agent 特殊性**：
- 由系统初始化时自动创建（per workspace），**不可软删**
- 有自己专用的 BaseClass（`cerebellum-baseclass`，系统内置神职）—— 见 §2 深海基因
- 不出现在 Workspace 节点的 Topology viz 拓扑图（仅在主脑视图显示）
- 心智状态通过 glow halos 显示（使用独立颜色 / 灰度调以区别普通 Entity）

### 8.3 三个 Tab 的统一规范

#### Tab 切换
- URL query：`?tab=entities|instances|blackboard`（默认 entities）
- 直接进入：`/workspaces/:id?tab=instances` 可深链
- Tab 切换时记录前一个 tab，用于"返回"行为

#### 加载态
- Tab 切换时：tab 内容区显示 spinner（不切换整个页面）
- 初次加载：整个 tab 内容区显示加载态

#### 错误态
- 整个 tab 内容区显示错误条 + "重试"按钮
- 切换到其他 tab 不影响

### 8.4 与其他页面关系
- **从空间列表**：点击卡片 → 进入详情页（默认 entities tab）
- **首次运行完成**：§6 引导第 3 步完成后跳转此处
- **眷族详情**：从 tab 1 卡片点击进入 `/entities/:id`（§13 学习页）
- **化身详情**：从 tab 2 行点击进入 `/workspaces/:id/instances/:iid`（§9）
- **拓扑**：从任何化身/眷族卡片的"在拓扑中查看"链接跳转到 `/workspaces/:id/topology`（§11）

---

## §9 化身详情页

### 9.1 路由
`/workspaces/:id/instances/:iid`

### 9.2 页面定位
- **入口**：空间详情"化身"tab 行点击、心灵图景节点点击、Composer 跳化身链接
- **场景**：操作员实时监控 1 个 AI 化身的运行状态、心智状态、事件流，并执行控制操作
- **典型职阶**：操作员（日常 Operator，重点）+ 审计者（拥有审计相关能力位的真人）

### 9.3 页面结构

```
┌──────────────────────────────────────────────────────────────┐
│ Header                                                        │
│   ← 返回空间                                                  │
│   化身标题：眷族名 + K8s pod 前缀                            │
│   副标题：神职 + rank + 当前 loop_status 实时显示            │
├──────────────────────────────────────────────────────────────┤
│ Status Bar（4 个 metric + 1 个 breaker config）               │
├──────────────────────────────────────────────────────────────┤
│ Control Toolbar（5 个控制按钮）                              │
├──────────────────────────────────────────────────────────────┤
│ Event Panel（最近 50 条印痕，按时间倒序）                    │
├──────────────────────────────────────────────────────────────┤
│ Snapshot Modal（按"快照"按钮时弹出）                         │
└──────────────────────────────────────────────────────────────┘
```

### 9.4 Header 详情

- **返回按钮**：左上方 `← 返回空间`，跳回 `/workspaces/:id?tab=instances`
- **大标题**：眷族 display name（链向眷族详情）+ K8s pod 前 8 位（mono 灰色）
- **副标题**：神职 chip + rank chip + 当前 loop_status badge（实时跟随 status poll）

### 9.5 Status Bar

4 个 metric 横排 + 1 个 breaker config：

| Metric | 显示 | 数据来源 | 实时刷新 |
|---|---|---|---|
| 心智状态 | badge（running/idle/paused/interrupted/completed/failed）颜色对应 glow | `loop_status` | 2s 轮询 |
| 续命次数 | 大字数字 | `continuation_count` | 2s 轮询 |
| 最近 checkpoint | ISO 时间戳或"从未" | `last_checkpoint_at` | 2s 轮询 |
| 熔断器配置 | 4 行 mini-table：max_cont / max_wall / max_token / idle_t | `breaker_config` | 加载时一次性 |

**未加载态**：每个 metric 显示 `—` + 灰色 spinner

### 9.6 Control Toolbar

5 个按钮水平排列（移动端可换行）：

| 按钮 | HTTP 方法 | 路径 | 触发动作 | 启用条件 |
|---|---|---|---|---|
| 中断 (Interrupt) | POST | `/instances/{iid}/interrupt` | 立即停止 loop，跳到 `interrupted` | 总是启用（除已 failed/completed）|
| 暂停 (Pause) | POST | `/instances/{iid}/pause` | 化身后台暂停，新 turn 入队 | 总是启用（除已 paused/failed）|
| 继续 (Resume) | POST | `/instances/{iid}/resume` | 从暂停处继续 loop | 仅 paused 时启用 |
| 状态 (Status) | GET | `/instances/{iid}/status` | 主动刷新 status（绕过轮询）| 总是启用 |
| 快照 (Snapshot) | POST | `/instances/{iid}/snapshot` | 生成 boulder snapshot，弹 modal | 总是启用 |

**按钮状态**：
- 默认：白底深灰边
- Hover：浅蓝底
- Busy（请求中）：显示 spinner + 文字「处理中...」，禁用其他按钮（避免并发）
- Disabled（条件不满足）：灰显 + tooltip 解释为什么禁用

**确认对话框**：
- 中断 / 暂停 / 炼化派生操作：弹确认 modal（参考 §13 蒸馏 UI 的 modal 风格）
  - 「确认中断？」 + 副标题「当前未保存的状态将丢失」
  - 「取消」/「确认中断」按钮
- 状态 / 快照：直接执行，无确认

**Toast 反馈**：
- 成功：绿色 toast「中断已发送」（自动消失 3s）
- 失败：红色 toast「中断失败：[error_message]」（带「重试」按钮）

### 9.7 Event Panel

**标题**：「事件流」+ 副标题「最近 50 条印痕」

**列表布局**：垂直列表，每条事件一行：
- 左：相对时间（"2 分钟前"）+ ISO 时间戳（mono 小字）
- 中：事件 type（mono 蓝色 chip）+ actor（`type/id` 格式）
- 右：payload 摘要（折叠展开）

**展开行为**：点击行 → 展开显示完整 JSON payload（等宽字体，深底浅字，预格式化）

**空态**：
- 标题："还没有印痕"
- 副标题："化身启动后事件会出现在这里"

**加载态**：列表上方显示 spinner + "加载事件中..."

**实时刷新**：每 2 秒追加新事件到顶部（不滚动整列表，只 prepend）

### 9.8 Snapshot Modal

按「快照」按钮弹出（也是 §6 引导里提到的 boulder snapshot）：

**Modal 结构**：
- 标题："化身快照"
- 副标题：`续命次数 N · 捕获时间 ISO`
- 主体：完整 JSON（深底等宽字体，可滚动）
- 右上角按钮：
  - 「复制到剪贴板」→ 绿色 toast「已复制」
  - 「关闭」X

**复制失败**：红色 toast「剪贴板不可用」+ 提供手动选中提示

### 9.9 错误态

| 场景 | 行为 |
|---|---|
| 化身不存在（404） | 跳回空间详情 tab=instances，红色 toast「化身不存在或已删除」 |
| 化身非本 workspace（403） | 跳回空间列表，红色 toast「无权访问此化身」 |
| 控制操作失败（500） | 按钮回到默认状态，红色 toast 显示具体错误 |
| 心智状态查询失败 | Status Bar 显示「连接中断」徽章，retry 按钮 |

### 9.10 与其他页面关系
- **从空间详情 tab=instances** 点击行进入
- **从心灵图景节点** 点击节点进入（带 transition 平滑滚动到 header）
- **从 Composer** 跳化身链接进入（URL hash 标记具体消息）
- **返回**：统一跳回 `/workspaces/:id?tab=instances`

---

## §10 Composer 页

### 10.1 路由
`/workspaces/:id/composer`

### 10.2 页面定位
- **入口**：Sidebar "Composer" 图标、心灵图景工具栏
- **场景**：操作员向 1 个或多个 AI 化身发送 turn（指令 + 命令 + 参数），跨眷族派活
- **典型职阶**：操作员（日常 Operator，重点）

### 10.3 页面结构

```
┌──────────────────────────────────────────────────────────────┐
│ Header                                                        │
│   "Composer" + "向一个或多个 AI 化身发送 turn"               │
├──────────────────────────────┬───────────────────────────────┤
│ 左侧：输入区                  │ 右侧：Compartments 预览       │
│  - textarea (大)              │  - 每条 @slug 一个卡片         │
│  - command autocomplete       │  - general 一个卡片           │
│  - send button                │  - 每张卡片展开命令和预设    │
└──────────────────────────────┴───────────────────────────────┘
```

### 10.4 左侧输入区

**Textarea**：
- 占满左侧高度（≈400px）
- 等宽字体（mono），方便看 `/cmd` 命令
- Placeholder："输入指令... 用 `@<slug> /<command>` 寻址 AI 化身"
- 实时 parse：输入时右侧 preview 同步更新

**Command Autocomplete**：
- 输入 `/` 时弹出下拉列表：
  - 全局命令：/read /list /write /archive
  - 控制命令（per-instance）：/interrupt /pause /resume /status /snapshot
  - 学习命令（per-entity）：/distill /consolidate /reflect
  - 神职专属命令（依当前眷族选中的神职过滤）
- 上下方向键选中，Enter 插入
- 当前选中的神职命令显示 description tooltip

**Send 按钮**：
- 位置：textarea 右下
- 状态：
  - 默认：蓝底白字"发送"
  - 可发送条件：parse 成功 + 至少 1 个 directive 或 general text
  - 不可发送：灰显 + tooltip "无内容或解析失败"
  - 发送中：spinner + "发送中..."
- 快捷键：`⌘ + Enter`（macOS）/ `Ctrl + Enter`（其他）

### 10.5 右侧 Compartments 预览

每条 `@<slug> /<command>` 解析后成为一个 compartment。预览规则：

#### 卡片类型

| 类型 | 标识 | 颜色边框 |
|---|---|---|
| `@<slug>` 定向 compartment | `@密士` / `@暗行` 等 | 蓝色（slate-300 → blue-500 左 border） |
| `general` 无定向 compartment | `General` | 灰色 |

#### 卡片内容

- **顶部**：左侧类型标签 + 右侧命令数 chip（"3 cmd(s)"）
- **中部**：该 compartment 的通用文本（若有）
- **命令列表**：每条命令一行
  - 命令名（mono 蓝色）：`/build`
  - 参数（若有）：灰色
  - content_ref（若有）：`ref: @workspace:path/to/file`
- **底部**（如有匹配神职）：展开显示该神职可用命令的 chip 列表（蓝色 chip 灰色 chip 紫色 chip 按族分组）

#### 空态

- textarea 为空时：右侧显示引导文案
  - 标题："开始输入以查看分割预览"
  - 副标题："每条 `@slug /cmd` 会成为一个独立的 compartment"
  - 示例：`@密士 /plan 帮我设计一个 RAG 系统`

### 10.6 发送后的行为

**成功**：
- 绿色 toast "已发送 N 个指令"（N = directive 数）
- textarea 清空
- 右侧 compartments 清空
- 跳转：可选——停留在 Composer / 跳到心灵图景（看化身开始 loop）/ 跳到第一目标化身详情

**失败**：
- 红色 toast "发送失败：[error_message]"
- textarea 内容保留
- 重试按钮（在 toast 上）

**Parse 失败**（如 `@密士` 但 slug 不存在）：
- 红色 toast "目标 `@xxx` 不存在"
- textarea 内容保留
- 跳转链接："前往眷族列表创建"（跳空间详情 tab=entities）

### 10.7 响应式

- 桌面（≥1024px）：左右 2 列
- 平板（768-1023px）：上下 2 列，textarea 占上方 60%
- 移动端（<768px）：只有 textarea + send 按钮；compartments 预览折叠到「预览 ▾」按钮点击展开

### 10.8 与其他页面关系
- **从心灵图景** 进入（带预填 `@<slug>` if 从节点发起）
- **从首次运行引导** 完成（清空 + 默认空 workspace 的引导已结束）
- **发送后**：跳转到对应化身详情或停留在 Composer（用户配置）
- **跨 Workspace**：Composer 是当前 Workspace 内派活，跨 Workspace 派活 P16d 后扩展

---

## §11 心灵图景页

### 11.1 路由
`/workspaces/:id/topology`

### 11.2 页面定位
- **入口**：Sidebar "拓扑" 图标、空间详情 "在拓扑中查看" 链接
- **场景**：可视化 AI 化身 / 真人契印之间的拓扑关系（节点 + 通道），通过 3 种交互模式操作
- **典型职阶**：全部真人观看（操作员 + 审计者 + Read-only 旁观者，§2.1）

### 11.3 页面结构

```
┌──────────────────────────────────────────────────────────────┐
│ Header                                                        │
│   "心灵图景" + 副标题 "拖动平移 · 滚轮缩放 · 事件每 2 秒刷新"│
├──────────────────────────────────────────────────────────────┤
│ Toolbar（3 个模式按钮）                                       │
│   [选择 V] [连接 C] [移动 M]                                  │
├──────────────────────────────────────────────────────────────┤
│ Canvas（SVG 全屏）                                            │
│   - 节点：圆形 + glow 颜色（对应 loop_status）                │
│   - 边：直线（passage 通道）                                  │
│   - 节点悬停显示 tooltip                                      │
│   - 选中节点高亮                                              │
├──────────────────────────────────────────────────────────────┤
│ NodeDrawer（选中节点时右侧抽屉）                              │
└──────────────────────────────────────────────────────────────┘
```

### 11.4 Header 详情

- 大标题：「心灵图景」+ Workspace slug（mono 小字）
- 副标题：「拖动平移 · 滚轮缩放 · 事件每 2 秒刷新」
- 右侧（可选）：节点总数 + 通道总数 + 实时 loop 化身数

### 11.5 Toolbar

3 个模式按钮横排（移动端折叠到右上角菜单）：

| 模式 | 快捷键 | 图标 | 行为 |
|---|---|---|---|
| 选择 (Select) | `V` | `MousePointer2` | 点击节点选中，弹出 NodeDrawer |
| 连接 (Connect) | `C` | `Link` | 点击源节点 → 点击目标节点 → 创建通道 |
| 移动 (Move) | `M` | `Move` | 拖拽节点改变位置（PATCH membership posx/posy）|

**当前模式高亮**：蓝底白字 + 顶部状态栏显示"当前：[模式]"

**Read-only 模式（P16d 扩展，目前未实现）**：所有模式按钮禁用，节点拖拽禁用；触发条件 = 用户缺少 `can_move_node` 等节点编辑能力位

### 11.6 Canvas

**节点类型**：
- **AI 化身节点**：圆形 40px 半径，外环 glow 颜色对应 `loop_status`：
  - running = 绿色（#10b981/strong）
  - idle = 黄色（#eab308/medium）
  - paused = 灰色（#94a3b8/weak）
  - interrupted = 橙色（#ef4444/medium）
  - completed = 蓝色（#3b82f6/low）
  - failed = 红色（#dc2626/strong）
- **真人契印节点**：圆形 40px 半径，纯灰底（slate-200），无 glow（真人无 loop 状态）
- **节点内图标**：化身 = `Bot`，真人 = `User`

**通道（Passage）边**：
- 直线连接两个节点
- 默认灰色（#94a3b8）1.5px
- 激活时（最近有消息传递）：绿色（#10b981）2px + 粒子动画（圆点沿直线移动 1s）

**交互**：
- **悬停**：节点边框高亮 + 浮出 tooltip（label | role | status）
- **拖拽**：在 Move 模式下拖动节点（实时跟随鼠标，松手时 PATCH 后端）
- **点击**：根据当前模式行为不同

**坐标系统**：
- posx/posy：用户自定义坐标（free-form Cartesian，无 grid 约束）
- 范围：理论无界；显示边界 = -1000 到 +1000
- 冲突检测：PATCH 时若 (posx, posy) 已被同 workspace 占用 → 409，节点回到原位 + 红色 toast

**Viewport 控制**：
- 拖拽空白处 = 平移整个画布
- 滚轮 = 缩放（0.25x - 4x）
- 移动端双指 = 平移 + 缩放

### 11.7 Connect 模式流程

1. 用户点击源节点 → 节点边框变橙（pending 状态），顶部出现提示条："点击目标节点"
2. 用户点击目标节点 → POST `/messaging/corridors` 创建 passage
3. 成功：新通道出现 + 节点边框恢复正常 + Toast "通道已建立"
4. 失败：节点边框回退 + Toast "通道创建失败：[error]"

**取消**：再次点击同一源节点，或按 `Esc`

### 11.8 NodeDrawer（右侧抽屉）

选中节点时出现，宽度 288px，从右滑入：

| 字段 | AI 化身节点 | 真人契印节点 |
|---|---|---|
| 类型 | "AI 化身" | "真人契印" |
| Label | 眷族显示名 | 真人用户名 |
| 角色 | 神职 + rank | 觉醒基因预设名（如 `operator-gene`） |
| 状态 | loop_status badge + glow 颜色块 | "在线/离线" 标记 |
| 坐标 | (posx, posy) | (posx, posy) |
| 操作 | "进入化身详情"（跳 §9）/ "软删除"（需 `can_delete_node`） | "查看成员信息" / "解除契印"（需 `can_remove_membership`） |

### 11.9 实时刷新

- 每 2 秒拉取 `/offices/{id}/live-status`，更新节点 glow 颜色
- 每 5 秒拉取 `/events?type_prefix=messaging.&since=5s_ago`，检查是否有 `messaging.message_sent` 触发对应通道的粒子动画
- 节点位置 / 通道存在性：每次操作后 refetch（无后台轮询）

### 11.10 与其他页面关系
- **从空间详情** tab 跳入
- **从化身详情** 通过 URL 参数进入（带 focus 节点）
- **从 Composer** 跨入（带 pre-selected 目标节点）
- **退出**：返回空间详情

---

## §12 调试页

### 12.1 路由
`/debug`

### 12.2 页面定位
- **入口**：Sidebar "Debug" 图标（无 workspace 依赖，全局入口）
- **场景**：操作员 / 审计者按类型/资源/时间过滤并查看 AI 化身产生的全部印痕（EventLog），支持导出
- **典型职阶**：审计者（拥有审计相关能力位的真人，重点）+ 操作员（偶发使用）

### 12.3 页面结构

```
┌──────────────────────────────────────────────────────────────┐
│ Header                                                        │
│   "调试" + "按类型与时间过滤，查看 AI 化身原始印痕"          │
│   右侧：[刷新] [导出 JSON]                                    │
├──────────────────────────────────────────────────────────────┤
│ Filter Bar（6 字段 + 3 个 quick pick + 时间范围 + 重置）      │
├──────────────────────────────────────────────────────────────┤
│ Events Table（5 列：时间/类型/操作者/资源/Payload 摘要）       │
└──────────────────────────────────────────────────────────────┘
```

### 12.4 Filter Bar

**6 个字段**（桌面 6 列，平板 3 列 × 2 行，移动端 1 列 × 6 行）：

| # | 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|---|
| 1 | type_prefix | text | `harness.` | 事件类型前缀 |
| 2 | resource_type | select | (all) | instance / office / membership / corridor / message / memory_entry / learning / blackboard |
| 3 | resource_id | text | (空) | UUID |
| 4 | request_id | text | (空) | UUID |
| 5 | since | datetime-local | (空) | 起始时间 |
| 6 | until | datetime-local | (空) | 结束时间 |

**3 个 type_prefix quick pick**（chip 按钮）：
- `harness.`（默认 + 高亮）
- `instance.`
- `messaging.`

**3 个时间范围 quick pick**（chip 按钮）：
- 最近 1 小时
- 最近 24 小时
- 最近 7 天

**重置按钮**：清空所有字段到默认

**应用按钮**：commit 当前过滤条件触发查询

### 12.5 Events Table

**5 列**：

| 列 | 内容 |
|---|---|
| 时间 | ISO 时间戳（mono） |
| 类型 | 事件 type（mono 蓝色） |
| 操作者 | `actor_type/actor_id`（蓝色 + 灰色） |
| 资源 | `resource_type:resource_id` 或 `-` |
| Payload | JSON 摘要（80 字符截断） |

**行交互**：
- 点击行 → 展开显示完整 JSON（深底等宽字体，预格式化）
- 再次点击 → 折叠

**空态**：
- 标题："没有匹配的印痕"
- 副标题："尝试调整过滤条件或扩大时间范围"

**加载态**：
- 表格头行下方 spinner + "加载印痕中..."

**轮询**：
- 每 5 秒自动刷新（应用过滤后启动轮询）
- 顶栏右侧 "Last updated 14:23:01" 提示

### 12.6 Header 操作按钮

**刷新**：手动触发当前过滤的查询（绕过轮询）

**导出 JSON**：
- 弹下载文件 `cocoa-events-<ISO时间戳>.json`
- 内容：当前显示的全部事件数组（不是全库）
- 含完整 payload（不仅是摘要）
- 导出后 Toast "已导出 N 条事件"

### 12.7 与其他页面关系
- 从化身详情跳过来（带预填 resource_type=instance + resource_id=iid）
- 从空间详情跳过来（带预填 resource_type=office + resource_id=wid）

---

## §13 学习页 + 蒸馏 UI

> **蒸馏 2 动作（命名严格确定）**：
> - **晋升 (promote)** — Instance → Entity，捕获当前运行中化身的 Memory 回写到所属眷族，原地增强眷族
> - **炼化 (transmute)** — Entity → BaseClass，将眷族累积的 Memory 蒸馏为新的可复用神职（跨 Workspace 可用）
>
> **没有第 3 个动作**（"飞升" / "ascend" 等不存在）。
>
> **与基因的关系**：蒸馏动作产生的是 **新 BaseClass（神职）**，不是深海基因。神职和深海基因是两个正交维度——神职定义 AI 的 prompt + commands + provider config；深海基因定义 AI 的 capabilities（skills / tools / mcps / lsps）。新 BaseClass 可以**引用**已存在的深海基因作为其默认安装包，但蒸馏产物本身 ≠ 基因。

### 13.1 路由
`/workspaces/:id/entities/:eid/learning`

### 13.2 页面定位
- **入口**：空间详情 tab=神职 卡片"学习"按钮、眷族详情
- **场景**：查看 AI 眷族的 Memory 汇总，并触发 2 个蒸馏动作（晋升 / 炼化）
- **典型职阶**：操作员（日常 Operator，重点）

### 13.3 页面结构

```
┌──────────────────────────────────────────────────────────────┐
│ Header                                                        │
│   眷族显示名 + 神职 + rank                                   │
│   副标题："Memory 汇总 + 晋升 / 炼化"                       │
├──────────────────────────────┬───────────────────────────────┤
│ 左：Memory 汇总               │ 右：蒸馏表单                   │
│  - 4 个 kind 计数卡          │  - action 选择（晋升/炼化）   │
│  - 最近 5 条 lessons          │  - 目标 slug 输入              │
│                              │  - kind 过滤多选              │
│                              │  - 源神职 slug（可空）         │
│                              │  - 触发按钮                   │
├──────────────────────────────┴───────────────────────────────┤
│ Result Modal（蒸馏完成后弹出，晋升/炼化产物预览）             │
└──────────────────────────────────────────────────────────────┘
```

### 13.4 Header 详情

- 大标题：眷族 display name（mono slug 在上方小字）
- 神职 chip + rank chip
- 副标题："Memory 汇总 + 晋升 / 炼化"

### 13.5 左：Memory 汇总

**4 个 kind 计数卡**（grid 2x2）：
- 经验 (experience) - 数字 + 图标
- 教训 (lesson) - 数字 + 图标
- 决策 (decision) - 数字 + 图标
- 问题 (problem) - 数字 + 图标

每个卡片：图标 + 大数字 + kind display name

**最近 5 条 lessons**（列表）：
- 每条 80 字符截断
- 灰底浅边
- 点击展开查看完整内容（modal）

**空态**：
- 标题："Memory 还是空的"
- 副标题："化身运行一段时间后会有经验 / 教训 / 决策记录"

**加载态**：spinner + "加载 Memory 中..."

**错误态**：错误条 + "重试"按钮

### 13.6 右：蒸馏表单

**Action 选择**（2 个 tab 或 radio）：
- **晋升**（promote）：Instance → Entity，捕获当前化身运行时 Memory 回写到眷族
- **炼化**（transmute）：Entity → BaseClass，将眷族累积 Memory 蒸馏成新神职

**根据 Action 切换表单字段**：

#### 晋升模式（promote）
- **目标 slug**：自动 = 当前眷族 slug，灰显不可编辑
- **Kind 过滤**（多选 checkbox）：可勾选 "仅晋升教训/决策/..."
- **触发按钮**：「晋升」 → POST `/learning/entities/{eid}/distill?action=promote`
- **说明 tooltip**：晋升会捕获当前眷族所有 running 化身的 Memory + 主脑写入，原地增强眷族自身 prompt

#### 炼化模式（transmute）
- **目标 slug**：必填，输入新 BaseClass 的 slug
  - 校验：`/^[a-z][a-z0-9-]*$/`
  - 实时去重检查
  - 显示 BaseClass slug 全名预览（自动加 `-skill-<timestamp>` 后缀避免冲突）
- **源神职 slug**（可选）：基于哪个已有神职 fork
- **Kind 过滤**（多选）：可勾选参与蒸馏的 Memory 类型
- **触发按钮**：「炼化」 → POST `/learning/entities/{eid}/distill?action=transmute`
- **说明 tooltip**：炼化会基于眷族累积 Memory 生成新的可复用神职，跨 Workspace 也能用

### 13.7 Result Modal（蒸馏完成）

按触发按钮后弹出，包含：
- 标题：「晋升完成」/「炼化完成」
- 副标题：摘要文案
- Manifest 预览（key-value 表格）：
  - 新 slug
  - 新 display name
  - 模型
  - prompt（前 2 行截断）
  - skills 列表
  - tools 列表
  - commands 列表
- 底部按钮：
  - 「关闭」
  - 「查看神职」→ 跳 `/workspaces/:id/entities`（炼化产物可作为眷族再次召唤）

**失败处理**：modal 切换为红色错误态，显示具体错误 + "重试"按钮

### 13.8 与其他页面关系
- **从空间详情 tab=神职** "学习" 链接进入
- **完成后**：跳转到新眷族（晋升）或返回空间详情（炼化）

---

## §14 觉醒基因 UI（人类侧 — 权限组管理）

> **作用域**：本节只讲**觉醒基因** UI（人类权限位组合）+ 能力位检查。**深海基因 UI 在 §14b**（AI 侧 capability 打包）。**严禁混为一谈**。

### 14.1 用户身份状态展示（Topbar）

| 元素 | 位置 | 显示规则 |
|---|---|---|
| 觉醒基因 chip | Topbar 用户名旁 | 当前生效的觉醒基因名（如 `operator-gene` / `admin-gene`），hover 显示能力位列表 |
| Super Admin badge | 用户名下方 | `user.is_super_admin === true` 时显示金色徽章（真人根权限标识，独立于基因预设） |
| 单能力位 tooltip | 鼠标悬停 | 显示该能力位的描述（"可召唤眷族"等） |

### 14.2 觉醒基因设置入口

入口在空间设置菜单（需 `can_manage_genes`）：

```
空间设置（⋯ 菜单）
├── 成员管理（Membership）
│   ├── 列出所有真人契印
│   ├── 每个成员显示：用户名 + 当前觉醒基因 + 能力位展开/收起
│   └── 操作：分配新基因 / 编辑能力位覆盖 / 解除契印
├── 觉醒基因管理
│   ├── 列出觉醒基因列表（built-in: operator / auditor / admin / viewer）
│   └── 操作：新建基因 / 编辑能力位组合 / 删除基因（built-in 不可删除）
└── 深海基因管理（§14b，跳转）
```

### 14.3 觉醒基因编辑界面

#### 列表视图
- 表格行：基因名 + 描述 + 能力位数量 + 「编辑」/「复制」/「删除」按钮
- 顶部「+ 新建觉醒基因」按钮

#### 单基因编辑视图

- **元数据**：
  - 基因名（必填，kebab-case）
  - 描述（多行文本，必填）
  - 标签：内置 / 自定义（只读）

- **能力位列表**（核心）：
  - 列出所有 `can_*` 能力位，每个有 checkbox
  - 已勾选的能力位属于此基因
  - 每行显示能力位 key + 人类语言描述（"召唤眷族" / "中断化身"）
  - 全选 / 全不选快捷按钮

- **预览**：
  - 右上角显示「此基因预期效果」摘要
  - 例：`operator-gene` = "可以召唤眷族、操作化身、编辑主脑；不能导出审计日志"

### 14.4 能力位参考表（v0 候选清单）

| Key | 描述 | 默认归属基因 |
|---|---|---|
| `can_summon_entity` | 召唤眷族 | operator |
| `can_spawn_instance` | spawn 化身 | operator |
| `can_interrupt_instance` | 中断化身 | operator |
| `can_pause_instance` | 暂停化身 | operator |
| `can_edit_central_hub` | 编辑主脑 | operator |
| `can_view_workspace` | 查看 workspace | operator / viewer / auditor |
| `can_view_topology` | 查看心灵图景 | operator / viewer / auditor |
| `can_view_audit_log` | 查看调试印痕 | operator / auditor |
| `can_export_audit_log` | 导出印痕 JSON | auditor |
| `can_manage_genes` | 管理基因预设 | admin |
| `can_create_workspace` | 创建 workspace | admin |
| `can_delete_workspace` | 删除 workspace | admin |

> 实际能力位清单待 15d-rename wave 后冻结。

### 14.5 运行时能力位检查

任何页面操作触发能力位缺失时：

- **缺失位时** UI 反馈：操作按钮置灰 + tooltip「需要能力位 `xxx`」
- **强行调用**（API 403）：跳 `/403` 页面
- **统一的 403 错误处理**（不在每个页面单独实现）

### 14.6 UI 元素权限对应表（觉醒基因侧）

| UI 元素 | 能力位依赖 |
|---|---|
| 「+ 召唤眷族」按钮 | `can_summon_entity` |
| 化身 5 个控制按钮 | 对应能力位（interrupt / pause / resume / status / snapshot 各一） |
| Workspace 设置菜单 | `can_manage_genes` 或 `can_create_workspace` 等 |
| 拓扑 3 模式 | 仅节点位置编辑需 `can_move_node`（P16d 后）/ 普通查看用 `can_view_topology` |
| 节点软删除 | `can_delete_node` |
| 调试页导出 JSON | `can_export_audit_log` |
| 蒸馏触发按钮 | `can_distill_entity`（晋升）/ `can_transmute_entity`（炼化） |
| 契印解除 | `can_remove_membership` |
| 深海基因编辑（§14b） | `can_manage_ai_genes`（与 `can_manage_genes` 不同） |

### 14.7 /403 页面（觉醒基因侧）

任意页面操作触发 403 时：
- 跳转到 `/403` 页面
- 标题："缺少能力位"
- 副标题："你当前的觉醒基因预设为 `[xxx]`，缺失能力位：`[yyy]`。请联系超管或申请权限"
- 「申请权限」按钮 → 联系超管（生成 `EventLog` 印痕作为申请记录）
- 「返回首页」按钮 → 跳空间列表

### 14.8 与其他页面关系
- 能力位提示散落在所有页面顶部 / 操作按钮处（灰显 + tooltip）
- 统一的 403 错误处理（不在每个页面单独实现）
- 觉醒基因变更产生 `EventLog` 印痕（operator → `EventLog.type = "human_gene.*"`）

---

## §14b 深海基因 UI（AI 侧 — Capability 打包管理）

> **作用域**：本节讲**深海基因**（AI capability 打包）UI。**严禁**与 §14 觉醒基因混淆——它们是 schema / UI / 生命周期都不同的两套系统。
>
> **入口**：空间设置菜单 → 深海基因管理（需 `can_manage_ai_genes`）。或 BaseClass 编辑界面勾选使用的深海基因。

### 14b.1 深海基因列表

入口：`空间设置 → 深海基因管理`

- 表格行：基因名 + kind（tool-gene / meta-gene / genome / workflow-gene）+ tags + 「编辑」/「查看 manifest」/「删除」按钮
- 顶部「+ 新建深海基因」按钮

### 14b.2 单深海基因编辑视图

#### 基础元数据
- 基因名（kebab-case）
- kind（4 选 1：tool-gene / meta-gene / genome / workflow-gene）
- 描述
- tags

#### Manifest 字段（按 kind 动态显示）

| 字段 | 适用 kind | 内容 |
|---|---|---|
| `skill` | tool-gene / workflow-gene | SKILL.md 完整内容（含 frontmatter：name / description / metadata.openclaw.always） |
| `tool_allow` | tool-gene / meta-gene | 工具白名单 list（每条 `nodeskclaw_*` 工具名 / OpenClaw 原生工具组） |
| `scripts` | tool-gene | Python CLI 脚本 dict（filename → 内容）—— 部署到容器文件系统 + chmod +x |
| `runtime_config` | 全部 | 运行时配置补丁（env + 浅合并到 openclaw.json） |
| `gene_slugs` | genome only | 引用其他基因 slug（genome 专用） |
| `config_override` | 全部 | 模板覆盖配置 |

#### 安装预览
- 「预览」按钮 → 在 mock 容器渲染安装步骤
  - skill → 写入路径 / 注册目录
  - tool_allow → 注册到 LLM tool 列表
  - mcp → 启动进程命令
  - scripts → 部署路径 + chmod 命令
  - runtime_config → 生成的 openclaw.json 片段

### 14b.3 BaseClass / Entity 关联

#### BaseClass 编辑界面
- BaseClass 编辑页多一个 tab：「深海基因」
- 列表展示所有深海基因，checkbox 勾选"安装到 Entity"
- 实时预览"勾选后此 BaseClass 派生 Entity 会带哪些 capability"

#### Entity 编辑界面
- Entity 详情页 readonly 显示已绑定的深海基因（来源 BaseClass）
- "添加额外基因" 按钮 → 弹模态选择额外添加的深海基因（覆盖默认安装列表）

### 14b.4 Instance 安装状态展示

入口：化身详情页 → "深海基因" tab

- 列出当前已安装到 Instance 容器的深海基因
- 每行：基因名 + kind + 安装时间 + 状态（installed / failed / uninstalled）
- 「+ 安装新基因」按钮 → 选择未装基因 → 触发安装流程（高成本，可能需要重启 Instance）
- 「移除」按钮 → 解除关联（不删除基因本身）

### 14b.5 深海基因来源

未来扩展：从 GeneHub 同步（参考 nodeskclaw `scripts/upload_seeds_to_genehub.py`）。当前 v0 全部本地维护。

---

## §14c 知识 UI（仅 Instance 侧）

> **作用域**：本节讲**知识系统**（仅 Instance 维度的 env / file 注入）。**严禁**与基因 UI 混为一谈——知识 ≠ 深海基因。

### 14c.1 知识列表（化身详情 → 知识 tab）

| 元素 | 描述 |
|---|---|
| env 列表 | key + value + 来源（用户手动 / 模板注入） + 「编辑」「删除」按钮 |
| file 列表 | 文件名 + 路径 + 大小 + 来源 + 「下载」「替换」「删除」按钮 |
| 「+ 添加 env」按钮 | 弹模态：输入 key=value → POST Instance runtime config |
| 「+ 上传 file」按钮 | 弹模态：选择文件 → 上传到 PVC → 关联 Instance |

### 14c.2 知识编辑影响

- 修改瞬时生效（无需重启 Instance）
- 每次变更产生 `EventLog` 印痕
- 详见 §2.3

### 14c.3 未来扩展（暂不计划）

详见 §2.3「未来扩展（暂不计划）」—— RAG / 向量数据库 / 知识继承均在当前 roadmap 之外。

---

## §15 i18n 覆盖矩阵 + 错误显示规范

### 15.1 i18n 覆盖矩阵

**两套 locale**：`en`（默认 fallback）+ `zh-CN`

**强制 i18n 字段**（任何用户可见文案必须走 i18n）：

| 命名空间 | 覆盖页面 | 关键 key |
|---|---|---|
| `common.*` | 全部页面 | `appName`, `loading`, `retry`, `superAdmin`, `operator`, `logOut` |
| `nav.*` | AppShell | `offices`, `topology`, `composer`, `learning`, `members`, `debug` |
| `workspace.*` | 空间列表 + 详情 | `title`, `noWorkspacesTitle`, `noEntitiesTitle` |
| `workspaceDetail.*` | 空间详情 | `tabEntities`, `tabInstances`, `tabCentralHub` |
| `entity.*` | 空间详情 + 学习页 | `noEntity`, `noInstance`, `distillHeading`, `skillSlugLabel` |
| `instance.*` | 化身详情 | `statusIdle/Running/Paused/Interrupted/Completed/Failed`, `interrupt/pause/resume/status/snapshot` |
| `composer.*` | Composer | `title`, `send`, `sending`, `sendFailed`, `parseError` |
| `topology.*` | 心灵图景 | `selectMode/connectMode/moveMode`, `failedCreate`, `dismissError` |
| `debug.*` | 调试 | `typePrefix`, `resourceType`, `since`, `until`, `apply`, `reset`, `refresh`, `export`, `loadFailed` |
| `errors.*` | 全部错误态 | `401/403/404/500/502/503/network/unknown/validation/requestFailed` |
| `language.*` | 全部页面 | `label`, `switchTo`, `current` |
| `onboarding.*` | §6 引导 | `step1Title/Step1Subtitle/Step2Title/Step3Title` |

### 15.2 翻译完整度要求

- 所有 zh-CN 翻译必须人工审阅，不允许机翻直堆
- 占位符插值：必须使用 i18next 的 `{{var}}` 语法
- 复数处理：`count` 区分单复数（如 1 个化身 / 5 个化身）
- 术语一致性：所有页面用同一份术语表（不允许某页面"Blackboard"另一页面"主脑"）

### 15.3 错误显示规范

#### 错误分类

| 类别 | HTTP 状态 | 用户文案 | UI 表现 |
|---|---|---|---|
| 未授权 | 401 | "会话已过期，请重新登录" | 自动跳 `/login` |
| 无权限 | 403 | "你当前的角色无权执行此操作" | 跳 `/403` 页 |
| 未找到 | 404 | "资源不存在或已删除" | Toast + 跳回列表 |
| 服务器错误 | 500/502/503 | "服务器错误，请稍后重试" | 红色 toast + retry 按钮 |
| 网络错误 | - | "网络错误，请检查你的连接" | 顶部错误条 + retry 按钮 |
| 验证错误 | 422 | "输入不合法：[具体字段]" | 表单字段下方红字 |
| 未知错误 | - | "发生未知错误，请稍后重试" | 顶部错误条 |

#### 错误显示组件（统一）

所有页面错误态使用统一组件 `<ErrorBanner />`：
- 顶部红色边框 + 红色背景
- 错误图标（`AlertCircle`）
- 错误文案（i18n key）
- 「重试」按钮（如果适用）
- 「关闭」按钮（如果可关闭）

#### ApiError → i18n 映射

`api.ts` 的 `ApiError` 必须根据 HTTP status 自动选择 `errors.*` 文案（**这是独立审查发现的关键 gap，15e 必须修复**）。

```ts
// 示例映射
switch (error.status) {
  case 401: return t('errors.401')
  case 403: return t('errors.403')
  case 404: return t('errors.404')
  case 422: return t('errors.validation')
  case 500: case 502: case 503: return t('errors.500')
  default: return error.message ?? t('errors.unknown')
}
```

### 15.4 可访问性

| 项 | 要求 |
|---|---|
| 颜色对比度 | WCAG AA 标准（≥4.5:1），glow 颜色在白底和深底都有足够对比度 |
| 焦点可见 | 键盘 tab 焦点必须有蓝色 outline |
| ARIA 标签 | 所有 icon-only 按钮必须有 aria-label |
| 语义化 HTML | `<button>` vs `<div>`、`role="alert"` for error 等 |
| 屏幕阅读器 | 加载态用 `aria-live="polite"`、错误态用 `aria-live="assertive"` |

### 15.5 响应式规范

| 断点 | 宽度 | 布局变化 |
|---|---|---|
| mobile | <768px | sidebar → bottom tab bar；card grid → 1 列；debug table → 列表卡 |
| tablet | 768-1023px | 部分 2 列；debug table 简化 |
| desktop | ≥1024px | 完整布局 |

---

## §5 文档结构（后续 Todo 索引）

- §1 产品概述（本节）✓
- §2 三层正交概念：职阶 / 能力 / 知识（本节）✓
- §3 命名对照表（本节）✓
- §4 全局 UX 原则（本节）✓
- §6 首次运行引导 + 神职卡片组（本节）✓
- §7 导航结构 + AppShell（本节）✓
- §8 空间列表 + 空间详情页（本节）✓
- §9 化身详情页（本节）✓
- §10 Composer 页（本节）✓
- §11 心灵图景页（本节）✓
- §12 调试页（本节）✓
- §13 学习页 + 蒸馏 UI（晋升 + 炼化 2 动作）（本节）✓
- §14 觉醒基因 UI（人类侧 — 权限组管理）（本节）✓
- §14b 深海基因 UI（AI 侧 — Capability 打包管理）（本节）✓
- §14c 知识 UI（仅 Instance 侧）（本节）✓
- §15 i18n 覆盖矩阵 + 错误显示规范（本节）✓

---

## 附录：F1-F4 最终验证

- **F1. 页面覆盖度** — 10 个页面 + 导航 + 引导 + 蒸馏 UI + 觉醒基因 / 深海基因 / 知识 UI 全部 text wireframe ✓
- **F2. 命名一致性** — 所有术语 grep 对照 `phase-15d-naming-system.md` 无偏离 ✓
- **F3. 决策追溯** — 每个 UX 决策尾部标注 U1-U8 引用（部分标记）⚠️
- **F4. Golden path 可走通** — 从首次注册到首次蒸馏完整复现 ✓

---

*§1-§15 完成 (Todo #1-#11)。15e PRD v1 初稿完毕，等待用户审阅+反馈。*