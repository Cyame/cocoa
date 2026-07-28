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
- 可关闭（用户可随时点 X / Esc / 背景关闭，结果：保持空态，下次再显示）
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

## §6.U 首次运行引导 UI 详写（start-work 落地用）

### 6.U.1 Modal 容器

**触发条件**（已在 §6.1 定义）：Workspace 空态 + 从未创建过任何 Entity

**容器规格**：
- 桌面 ≥768px：`max-w-2xl`（672px）× auto height，居中 fixed，`z-50`
- 移动端 <768px：全屏 bottom sheet（top: 10vh, bottom: 0, border-t rounded）
- 背景 overlay：`bg-slate-950/50`，点击 overlay 关闭 modal（可关闭，已在 §6.2 确认）
- 内容区：white bg + rounded-xl + shadow-2xl + p-6（desktop）/ p-4（mobile）
- Enter 键 = 当前步"下一步"/"完成"（如果 button enabled）

**步骤指示器**：右上角 pill-style `步骤 1/3`（灰色）+ 当前步高亮（蓝色 ring）

**错误态全步骤统一**：
- 网络错误 modal → 背景 dim 30% + 当前步骤不清空 + 顶部 red banner "网络错误，请重试" + 「重试」按钮
- 提交错误（409 slug 冲突等）→ 表单字段下方红字 + "重试" 按钮停在当前步
- 意外错误（5xx）→ 黄色 warning banner "抱歉，召唤失败。已记录错误，后台处理中。" + 「关闭 + 稍后再说」

### 6.U.2 Step 1 神职选择 UI

**神职卡片 grid**：

| 桌面 | 平板 | 移动 |
|---|---|---|
| 3 列 (`grid-cols-3`) | 2 列 | 1 列 + 水平 swipe |

**每卡片尺寸**：280×320px（desktop）/ 240×300px（tablet）/ full width（mobile）

**卡片视觉层次（顶→底）**：
```
┌──────────────────────────┐
│   神职图标（24px lucide）│
│   神职 display name (H3) │
│   slug (mono, 灰色)      │
│                          │
│   1 句话职能描述 (14px)  │
│                          │
│   ┌─ 命令 chips ─┐      │
│   │ /plan  /build  │      │
│   │ /execute        │      │
│   └───────────────┘      │
│                          │
│   组标签 chip(蓝/绿/紫)  │
│   Provider: claude-3.5   │
└──────────────────────────┘
```

**卡片状态**：
- **默认**：`border-slate-200 bg-white`
- **选中**：`border-blue-500 ring-2 ring-blue-500/20 shadow-md translate-y-[-2px]`
- **hover**：`border-slate-400 shadow-md`（非选中）/ `border-blue-600`（已选中）
- **disabled**（v1 无这一级；保留以便 P16d 扩展）

**命令 chips**：
- 3 个 chips 水平排列，间距 1
- 每个 chip：`border-blue-100 bg-blue-50 text-blue-700 font-mono text-xs rounded-full px-2 py-0.5`
- hover → 显示该命令的完整 description tooltip（在 chip 上方 8px，白底灰边）

**分组 filter pills**（顶部，可选）：
```
[全部] [策划] [执行] [审视]
```
- active pill: `bg-blue-600 text-white`，rest: `bg-slate-100 text-slate-600 hover:bg-slate-200`
- 选择某个组 → 只显示该组的卡片（宽度短，居中）

**键盘操作**：
- `Tab` 选择下一个 card
- `Arrow` 上下左右导航
- `Enter` 选中 + focus "下一步"
- `Esc` 取消选择

**底部操作**：
- 「下一步」按钮：`disabled:opacity-50` + tooltip "请选择一个神职"（当未选中） / `bg-blue-600 text-white`（选中）
- 「稍后再说」链接：`text-slate-500 underline` → 关闭 modal + toast "已跳过引导"

### 6.U.3 Step 2 眷族创建表单 UI

**表单布局**：
```
┌───────────────────────────────────────┐
│ ┌─ 眷族显示名 ────────────────────┐  │
│ │ [____________________________]  │  │  实时去重：已占用 → 红框 + "该 workspace 已有同名眷族"
│ │ 例如：奈亚探子、克总助理         │  │
│ └──────────────────────────────────┘  │
│                                        │
│ ┌─ Slug (自动生成) ──────────────┐   │
│ │ [nai-ya-tan-zi_____________]   │  │  自动生成：当用户输入 display_name 时
│ │ kebab-case，小写字母开头         │  │  自动 slugify（去空格转小写插连字符）
│ └──────────────────────────────────┘  │
│                                        │
│ ┌─ Rank 选择 (radio) ─────────────┐  │
│ │ ◉ 深潜者（researcher）                │  │  默认选项
│ │   AI 持久化 + Memory 跨化身 ──────  │
│ │ ○ 浅识者（intern）                     │  │
│ │   AI 无状态，每次重启              │  │
│ └──────────────────────────────────┘  │
│                                        │
│ ┌─ 创建后冻结提示 ────────────────┐  │
│ │ ⚠ 上述属性创建后将冻结。如需改 │  │
│ │ 变，请新建 Entity。             │  │
│ └──────────────────────────────────┘  │
│                                        │
│         [上一步]    [召唤眷族]       │
└───────────────────────────────────────┘
```

**表单验证规则**：
| 字段 | 验证 | 反馈 |
|---|---|---|
| display_name | 必填 1-32 字符；同 workspace 不可重名 | 实时去重 + 红色 tooltip |
| slug | 自动生成非空；手动编辑时匹配 `/^[a-z][a-z0-9-]*$/`；同 namespace 全局 unique | 红色 tooltip + SlugInput 自带 invalid shaker animation |
| rank | 2 选 1（无必填校验，总是默认深潜者） | — |

**右侧预览区**（desktop/tablet only，移动端折叠到下方）：
- 实时渲染该 Entity spawn 后的化身卡片（含 rank badge + display_name + 神职 chip）
- 用静态 SVG preview（非真正 API call）

**「召唤眷族」按钮状态机**：
1. **disabled**（表单任一字段 valid 未过）→ 置灰 + "请完成所有必填项"
2. **enabled** → 蓝色 + "召唤眷族"
3. **submitting** → spinner + "召唤中..."
4. **success** → 绿色 check + auto-advance 到 Step 3（delay 500ms）
5. **error** → 表单不动，顶部 red banner + retry

### 6.U.4 Step 3 打招呼 + 首发消息 UI

**聊天区域**：
- textarea（不可编辑，只读显示 `@<slug> 你好，认识一下。`）
- 不可删除 / undo / insert
- 「发送」按钮（默认 disabled——用户必须点"发送"才开始 talk）

**"发送"后行为**：
1. loading spinner + "化身回复中..."
2. 一旦收到响应 → 显示该化身的首次回应（完整 markdown，可选中复制）
3. 回复区域自动 scroll to bottom
4. delay 500ms → "再发一条" + "完成" 两个并排按钮出现

**错误态**：
- 化身没回应（timeout 15s）→ "无响应" banner + retry（POST 同一消息）+ skip（"直接跳到新化身页面"）
- 网络错误 → "发送失败" toast + 「重试」按钮

**按钮**：
- 「再发一条」→ 清空回复 + 重置发送区域为 clean state
- 「完成」→ 关闭 modal + 跳 `/workspaces/:id?focus=memory&entity=:eid`（workspace dashboard 记忆 tab 定位新眷族）

---

## §7 AppShell + Sidebar 框架（VSCode 风）

> **15d 重构（2026-07-28）**：从"3-tab 详情页"转向"VSCode 风 IDE 布局"——Workspace dashboard 默认画布 = 拓扑图，常驻右侧 Composer panel，可折叠左侧 Sidebar 活动栏，节点点击弹大窗。

### 7.1 整体结构（3 浮层 + 1 主画布）

```
┌───────────────────────────────────────────────────────────────┐
│ AppShell - 全屏 IDE 布局                                         │
│ ┌────────┬──────────────────────────────────────────┬──────────┐│
│ │        │ Activity Bar（顶部）                    │          ││
│ │ Sidebar│ ┌────────────────────────────────────────┐ │ Composer ││
│ │ (左,    │ │ Tab 栏（多 tab 可切换）            │ │ Side     ││
│ │ 可折叠)│ │  [拓扑] [契印] [化身] [记忆]  ← 默认│ │ Panel    ││
│ │        │ ├────────────────────────────────────────┤ │ (右,     ││
│ │        │ │ 主画布（默认 = 拓扑 SVG 画布）        │ │ 常驻,    ││
│ │        │ │  click 节点 → 浮窗（背景 blur）       │ │ 可拖缩,  ││
│ │        │ │  dblclick 节点 → 持久化 tab          │ │ 可全屏,  ││
│ │        │ │                                      │ │ 可关闭)  ││
│ │        │ └────────────────────────────────────────┘ │          ││
│ │        │ Status Bar（底部 — 心智状态 / 超管)    │          ││
│ └────────┴──────────────────────────────────────────┴──────────┘│
└───────────────────────────────────────────────────────────────┘
```

4 个浮层 / 区：

| 区 | 默认状态 | 行为 |
|---|---|---|
| **Sidebar（左侧活动栏）** | 折叠（仅图标） | 默认 64px 宽，点按钮展开到 240px。包含 6 个图标：空间 / 神职市场 / 契印 / 眷族 / 调试 / 用户菜单 |
| **主画布（中间）** | 始终显示 | 多 tab 模式。默认 tab = 拓扑图（dashboard）。其他 tab = 契印 / 化身 / 记忆 |
| **Composer Side Panel（右侧）** | 常驻显示（默认宽度 360px） | 可拖拽边缘缩放（100-800px 范围），可全屏覆盖主画布，可折叠隐藏 |
| **Status Bar（底部）** | 始终显示 | 当前 Workspace 健康度 + 当前用户觉醒基因 chip + Super Admin badge |

### 7.2 Sidebar 活动栏（左侧）

**位置**：固定左侧，宽度 64px 折叠态 / 240px 展开态

**折叠态（默认）**：
- 6 个垂直堆叠图标（lucide 24px）：
  - `Building2` 空间（点击跳 `/namespaces` namespace 主页）
  - `Library` 神职市场（跳 `/base-classes`）
  - `Stamp` 契印管理（跳 `/contracts` global）
  - `Users` 眷族管理（跳 `/entities` global）
  - `Bug` 调试（跳 `/namespaces?tab=debug`）
  - `User` 用户菜单（点击展开用户菜单弹出层）
- 顶部：图标按钮 hover 显示 tooltip + 当前活动页背景高亮（蓝色 600）
- 底部：用户头像（点击展开用户菜单）

**展开态（240px）**：
- 与 VSCode 类似，2 个浮动 panel：
  - 左：图标列（同折叠态）
  - 右：图标对应的"二级"列表（如点击 `Building2` 显示 workspace 列表、`Users` 显示眷族列表、`Stamp` 显示契印列表）
- 视觉风格：白底 / 灰底 + 1px 边框

**Sidebar 切换 workspace**：
- 在展开态下点 workspace 卡片 → 切到该 workspace dashboard
- 双击 workspace 卡片 → 全屏打开 dashboard（隐藏 sidebar / status bar）
- 再次双击 → 还原 sidebar + status bar

### 7.3 主画布的多 tab 系统

**Tab 列表（默认）**：
```
[拓扑] [契印] [化身] [记忆]   (主画布 tab 栏)
```

**Tab 行为**：
- **切换 tab**：仅切换主画布内容，sidebar / composer panel 不动
- **持久化**：用户拖入新 tab 后，切其他 tab 回来仍在那里
- **关闭 tab**：右上角 `×` 按钮（节点双击开窗时的 tab）

**主画布默认 tab = 拓扑图**（§11 dashboard 视图）

#### 各 tab 内容速览

| Tab | 渲染对象 | 关键交互 |
|---|---|---|
| **拓扑**（默认） | SVG 画布 + 节点 + 通道 | hover tooltip / click 浮窗 / dblclick 持久化 tab |
| **契印** | 当前 Workspace 真人契印列表（表格） | 表格行 hover 高亮 + 右键菜单 |
| **化身** | 当前 Workspace 化身列表（card grid） | card hover 详情，click → 该化身 info tab 浮窗 |
| **记忆** | 眷族记忆聚合视图（按眷族分组） | 列表点击 → 单眷族记忆详情（窗内浮窗） |

### 7.4 Composer Side Panel（右侧）

**位置**：右侧固定栏，默认宽度 360px

**常驻行为**：
- 进入 workspace dashboard 时**自动展开**到 360px（不折叠可关闭但默认显示）
- 用户输入或对话历史可见，用户可关掉但下次进入 workspace 仍默认展开

**可调节交互**：
- **拖拽左边框**：横向 resize，宽度范围 100-800px
- **折叠按钮**：右上角折叠图标（→ side panel 收起为 0，主画布占满右侧）
- **全屏按钮**：右上角全屏图标（→ side panel 覆盖整个 viewport，含 sidebar / status bar / 主画布）
- **退出全屏**：Esc 键 或 全屏状态下点击右上角还原按钮

**视觉层次**（3 层）：
```
点击 Composer 浮窗 →
  Layer 1（背景）：主画布 blur(8px) + 暗化 30%
  Layer 2：Composer full-screen 浮窗
  Layer 3：SVG 节点浮窗（如果点击节点）
```

### 7.5 Status Bar（底部）

**位置**：底部固定，高度 24px

**结构**（从左到右）：
- Workspace 名（hover 显示完整 slug + 创建时间）
- Workspace 健康度指示（绿/黄/红，基于化身 loop_status 聚合）
- 分隔符
- 当前选中节点（如果在拓扑 tab 上有点击选中）
- 分隔符
- 右侧：觉醒基因 chip + Super Admin badge（如适用）+ 用户菜单

### 7.6 全局快捷键

| 快捷键 | 行为 |
|---|---|
| `⌘K` / `Ctrl+K` | 打开全局命令面板（搜功能 / 跳页 / 调起操作） |
| `Cmd+\` | 折叠 / 展开 Composer Side Panel |
| `Cmd+B` | 折叠 / 展开 Sidebar |
| `Cmd+Shift+F` | Composer 全屏 |
| `V` / `C` / `M` | 拓扑 tab 操作模式切换（仅在拓扑 tab 激活时） |
| `R` | 刷新当前 tab 数据 |
| `Esc` | 关闭浮窗 / 退出 Composer 全屏 |

### 7.7 路由总览

| 路由 | 页面 | 默认行为 |
|---|---|---|
| `/login` | 登录页（不在 AppShell 内） | 登录成功 → 跳 `/namespaces` |
| `/namespaces` | **namespace 主页（VSCode-style dashboard）** | 登录默认落点 |
| `/namespaces?tab=...` | namespace 主页的特定 tab（Workspace / 神职 / 契印 / 眷族 / 调试） | |
| `/workspaces/:id` | **Workspace dashboard**（VSCode-IDE 布局） | 进入此路由时 sidebar/Composer panel 自动展开 |
| `/workspaces/:id?fullscreen=:iid` | workspace dashboard 全屏打开指定化身 | |
| `/workspaces/:id?focus=memory&entity=:eid` | workspace dashboard "记忆" tab + focus 到指定眷族记忆 | |
| `/contracts` | 全局契印管理（VSCode 风，tab 化列表） | sidebar 契印图标 |
| `/entities` | 全局眷族管理（VSCode 风，列表 + 详情） | sidebar 眷族图标 |
| `/base-classes` | 神职市场（VSCode 风，grid + 详情） | sidebar 神职图标 |
| `/debug` | 调试页 | sidebar 调试图标 |

### 7.8 Namespace 主页（`/namespaces`）详

> 后续 §8 详写。当前简述：从 workspace 列表视角升级为 namespace dashboard。

**默认 tab = Workspace**（登录后第一次看到）：
- 上半部：Workspace 列表卡片 grid（每个 workspace 显示当前统计 + Stat 卡片 = 眷族数 / 化身数 / 主脑活跃状态）
- 下半部：召唤 CTA（如空）+ 召唤历史

**其他 tab**：
- **神职**：全球神职市场（11 + 可能的可装）
- **契印**：契约管理 + 觉醒基因分布表
- **眷族**：全局眷族设置（v1 简化版 — 主要在 workspace 层使用）
- **调试**：印痕流 + 过滤

### 7.9 未授权与未选 Workspace 处理

| 场景 | 行为 |
|---|---|
| 未登录访问受保护路由 | 跳 `/login` |
| 已登录但未选 Workspace | 跳 `/namespaces`（namespace 主页是登录默认落点） |
| 已登录，Workspace ID 无效（404） | 跳 `/namespaces`，Toast「Workspace 不存在或已删除」 |
| Token 过期（API 返回 401） | 清 token + 跳 `/login`，Toast「会话已过期，请重新登录」 |
| Composer 全屏状态下 token 过期 | 同上 + Composer 折叠回 side panel 形态 |

### 7.10 错误边界

- AppShell 整体包一个 `ErrorBoundary`
- 任意子组件崩溃 → 显示降级 UI："页面遇到错误，请刷新或返回首页"
- 提供「刷新」+「返回 /namespaces」按钮
- Composer 全屏状态下崩溃 → 默认 fallback 到 side panel 模式

### 7.11 响应式断点

| 断点 | 范围 | 布局 |
|---|---|---|
| mobile | <768px | Sidebar 折叠态强制 + Composer 折叠为底部 drawer；主画布仍 tab |
| tablet | 768-1023px | Sidebar 可折叠，Composer 默认 320px |
| desktop | ≥1024px | 完整 VSCode 风布局 |

> **v1 优先桌面**：mobile 体验是 fallback，不优化。

---

## §8 Namespace 主页（`/namespaces`）

> **核心定位**：登录后**默认落点**。这是系统最上层的"管理控制台"——VSCode 风布局，所有静态资产管理在这里。

### 8.1 总体结构

```
/namespaces 默认 tab = Workspace
/namespaces?tab=base-classes  → 神职市场
/namespaces?tab=contracts     → 契印管理
/namespaces?tab=entities     → 眷族管理（全局配置层）
/namespaces?tab=debug         → 调试
```

每个 tab 内容都在主画布显示，sidebar / composer panel 行为跟 workspace 一致（跨 tab 共享 IDE 布局）。

### 8.2 Workspace tab（默认）

**页面定位**：所有 workspace 的列表视图 + 召唤 CTA

**结构**：
- 顶部 stats 总览：当前 namespace 下 workspace 数 / 总眷族数 / 总化身数 / 总主脑活跃数
- 主区：workspace 卡片 grid（3 列 desktop / 2 列 tablet / 1 列 mobile）
- 每个卡片内容：
  - 大标题：Workspace 显示名
  - 副标题：slug + 创建时间
  - 4 项统计：当前眷族数 / 化身数 / 契印数 / 主脑健康度
  - 健康度 badge：绿（healthy）/ 黄（部分 idle）/ 红（有 failed 化身）
  - CTA：「进入 Workspace」按钮（点击 → /workspaces/:id，VSCode dashboard 展开）

**空态**（workspace 数为 0）：
- "还没有 Workspace" CTA：「召唤第一个眷族」（→ §6 引导）

### 8.3 神职 tab

**页面定位**：神职市场（base-classes）

**结构**：
- 顶部：分类过滤（4 类 / 全部）+ 标签过滤 + 排序
- 主区：神职卡片 grid
- 每卡内容：
  - 神职 display name + slug + 1 句话职能
  - 3 个核心命令 chip
  - Provider 默认（gpt-4o-mini / claude-3-5-sonnet 等）
  - 当前使用此神职的眷族数
  - CTA：「查看详情」

**点击卡片**：
- 单击 → 详情浮窗（不离开 tab 列表）
- 双击 → 全屏打开神职详情页

#### 神职详情浮窗

- 神职显示名 + slug + 1 段职能描述
- 命令全集（不带 3 个限制，全部列出 + hover tooltip）
- Provider 默认 + override 字段
- prompt 片段预览（前 200 字）
- 依赖的深海基因列表（v1 可能空）
- 来源 / 版本
- 底部 CTA：「基于此神职召唤眷族」→ §6 引导 Step 1 预选此神职

### 8.4 契印 tab

**页面定位**：全局用户契印管理

**结构**：
- 表格：用户名 / 觉醒基因 / 加入时间 / 状态
- 工具栏：「+ 添加契印」按钮（v1 可能 disabled / 仅超管）

**点击行**：
- 详情浮窗：契约详情 + 能力位覆盖

> **v1 简化**：契印由系统注册流程创建，不在 UI 上"手动添加"。

### 8.5 眷族 tab（全局配置层）

> **重要**：眷族管理 ≠ 眷族使用。**使用**在 workspace dashboard（§13 记忆 + 节点跳详情），**配置**在这里。

**页面定位**：眷族元数据 + 跨 workspace 全局视图

**结构**：
- 表格：眷族显示名 / slug / 神职（chip）/ rank / 关联 workspace / 化身数 / 记忆条数 / 创建时间
- 每行右侧操作：
  - 「详情」→ 浮窗显示完整属性
  - 「绑定深海基因」→ §14b
  - 「炼化」→ 跳到该眷族所在 workspace 记忆 tab
  - 「软删」（需 `can_summon_entity`）

**眷族详情浮窗**（嵌入 namespace tab，不离开主画布）：
- **基本属性**（可编辑）：
  - name / slug / display name
  - description（多行文本）
  - rank（创建后冻结）
  - BaseClass 关联（fixed after creation；不可修改）
- **深海基因**：当前 list + "添加额外基因"按钮（→ §14b）
- **当前化身列表**：每个化身的 loop_status badge + spawn 时间 + 「跳到化身」（跳到所在 workspace 仪表 + focus 节点）

### 8.6 调试 tab

详见 §12。Namespace tab 提供与 workspace 调试同等的印痕流，但粒度为 namespace 全局。

---

## §8.U Workspace 召唤 + 管理 UI 详写（start-work 落地用）

### 8.U.1 Workspace tab 卡片

**统计总览**（namespace 主页 Workspace tab 顶部 stats bar）：
```
┌──────────────────────────────────────────────────────────┐
│ 当前 namespace: 1 workspace · 5 眷族 · 3 化身 · 主脑活跃  │
│ [刷新]                                           [召唤新眷族] │
└──────────────────────────────────────────────────────────┘
```

- 「刷新」：手动 refetch workspace stats（不轮询，手动触发）
- 「召唤新眷族」：主 CTA → 触发 §6 modal（如果 workspace 是空态则直接展示 Step 1）

**Workspace 卡片渲染**（3 列 desktop grid）：

每卡内容：
```
┌──────────────────────────────────────┐
│ 大标题 (H2)        [健康度 badge]      │
│ slug (mono, 灰色)                     │
│                                       │
│ 4 项统计 grid (2×2)                  │
│ ┌──────────┐ ┌──────────┐            │
│ │ 眷族: 5  │ │ 化身: 3  │            │
│ └──────────┘ └──────────┘            │
│ ┌──────────┐ ┌──────────┐            │
│ │ 契印: 2  │ │ 主脑: 240KB│          │
│ └──────────┘ └──────────┘            │
│                                       │
│ [进入 Workspace →]                    │
└──────────────────────────────────────┘
```

健康度 badge：左边 colored circle 8px + 文字 small：
- 绿 = 所有化身 running / idle
- 黄 = 有 paused / interrupted 化身
- 红 = 有 failed 化身

点击任意位置 → 进入该 workspace dashboard（`/workspaces/:id`）。

### 8.U.2 Workspace 空态（namespace 主页 Workspace tab 为 0 时）

```
┌──────────────────────────────────────────────┐
│ 🏢                                           │
│ 还没有 Workspace                          │
│ 召唤第一个眷族，让 AI 化身给你干活 →        │
│                                              │
│ [召唤首位眷族]  (触发 §6 modal)               │
│                                               │
│ 或者浏览神职市场，先了解 11 位 AI 专家 ▸     │
└──────────────────────────────────────────────┘
```

- 居中，与 §6 引导一致的视觉风格
- "或者浏览神职市场" → 跳 `/namespaces?tab=base-classes`

### 8.U.3 Workspace 详情（dashboard）顶部 header

**Header 条**（workspace dashboard 顶部，sticky）：

```
┌──────────────────────────────────────────────────────────────┐
│ │ Workspace 显示名                        [召唤眷族]  [⋯]  │
│ │ slug · 创建于 1 天前 · 你                                  │
│ │ 5 眷族 · 3 化身 · 主脑 240KB         [健康度 / 全屏 / 刷新] │
└──────────────────────────────────────────────────────────────┘
```

- 「召唤眷族」：primary 按钮 → 触发 §6 modal（pre-fill 当前 workspace 上下文）
- 「⋯」菜单（需 `can_manage_workspace`）：编辑名 / slug / 软删除（30 天）+ "批量重启 outdated 化身"（如果有）
- 健康度 badge：同 card 一样的逻辑
- 全屏按钮：点击 → workspace dashboard 全屏（隐藏 sidebar / status bar / composer panel；点击同一按钮 / Esc 退出全屏）

### 8.U.4 批量重启 outdated 化身 UI

**触发**：Header 「⋯」→ 批量重启 outdated 化身

**全屏 modal**（desktop 800px wide / mobile bottom sheet）：

```
┌──────────────────────────────────────────────┐
│ 批量重启 outdated 化身                        ✕ │
│ 当前 2 / 5 化身 hash 不匹配                  │
│                                              │
│ 化身列表：                                   │
│ □ AI-1 (paused#abc12345)      outdated 3h   │  ← 选中
│ □ AI-2 (idle#def67890)        outdated 1d   │  ← 选中
│ ☐ AI-3 (running#ghi90123)     active 2m     │  ← 跳过（正在运行，禁选）
│                                              │
│ [全部选中 / 全不选]               [确认重启 2 个化身] │
│                                              │
│ 确认后：化身将停止当前 loop，pod 重创建，新 │
│ 能力自动装入。Memory 不会被回收。           │
└──────────────────────────────────────────────┘
```

- 每个化身行右侧显示 running/idle/paused/failed + outdated 时间戳
- **禁选**：running 状态的化身不参与批量重启（正在运行，需要用户先手动停止）
- hiking 逻辑：选中项默认 sorted by outdated duration（最旧排第一）
- 「确认重启 N 个化身」→ spinner + progress bar（每个化身一个 step）→ 完成 green toast

**单化重重启**（拓扑图 outdated 节点浮窗 →「重启以更新」按钮）：
- 与该化身 outdated 节点浮窗共享同一个 RESTART endpoint
- 弹 modal 确认："重启 Instance #XXX？当前 loop 将停止，pod 重创建"——等同于批量重启的单例版本

### 8.U.5 空态召唤（workspace 无眷族时主画布 CTA）

如果 workspace dashboard 有 0 眷族，主画布（当前 tab）应显示召唤 CTA：

```
┌──────────────────────────────────────────┐
│ 该 Workspace 还没有 AI 眷族             │
│ 召唤第一位眷族，从 11 神职中挑选 →     │
│                                          │
│ [召唤首位眷族]  [跳过进入 workspace 概览]   │
└──────────────────────────────────────────┘
```

- 所有 4 个 tab（拓扑 / 契印 / 化身 / 记忆）都显示同一个空态 CTA
- 「召唤首位眷族」→ 触发 §6 modal
- 「跳过进入 workspace 概览」→ 切到 Workspace 页面（namespace Workspace tab）保持空态

### 8.U.6 删除 Workspace 确认

**触发**：Header 「⋯」→ 软删除 workspace

**确认 modal**：
```
确认删除 [workspace name]？
该 workspace 内所有眷族 (5)、化身 (3)、记忆、契印都将保留，
但其 members 将不再能访问。30 天内可恢复。
[取消]  [确认软删除]
```

- 确认 → toast "Workspace 已软删除" + 跳 `/namespaces`
- 取消 → 返回 workspace

---

## §9 Workspace Dashboard（`/workspaces/:id`）

### 9.1 页面定位

workspace 进入后的主页面 = VSCode 风 dashboard，**默认主画布是拓扑图**。

### 9.2 默认状态 = 拓扑 dashboard（详见 §11）

- 渲染 SVG 节点画布（契印节点 + 眷族节点 + 主脑节点）
- 节点 hover → tooltip（loop_status 心智状态）
- 节点 click → 浮窗
- 节点 dblclick → 持久化 tab

### 9.3 主画布的 4 个 tab

| Tab | 默认 | 内容 |
|---|---|---|
| 拓扑 | ✓（默认） | §11 SVG dashboard |
| 契印 |  | 当前 workspace 真人契印列表（表格，简化版） |
| 化身 |  | 当前 workspace 化身列表（card grid，含 loop_status glow） |
| 记忆 |  | 眷族记忆聚合视图（按眷族分组，记忆数 / 最近晋升 / 最近炼化） |

#### 契印 tab

表格：用户名 / 觉醒基因 / 加入时间

#### 化身 tab

- card grid：每张卡显示节点类型 + 眷族信息
- 每行操作：「跳到记忆详情」/「软删除」（需权限）

#### 记忆 tab

- 眷族维度分组（按眷族 list）
- 每个眷族卡片：当前 Memory 统计 + 上次晋升 / 炼化时间
- 卡片点击 → 单眷族记忆详情浮窗（§13）

---

## §10 Composer Side Panel

### 10.1 路由 / 触发

- 进入 workspace dashboard 时**自动展开**右侧 Composer panel（常驻 360px）
- 用户随时可通过快捷键 `Cmd+\` 折叠 / 展开
- 「全屏」按钮可让 Composer 覆盖全 viewport（含 sidebar + 主画布 + status bar）

### 10.2 常驻面板布局

```
┌─────────────────────────────────────┐
│ Composer Panel（360px 宽，可拖）       │
├─────────────────────────────────────┤
│ Header                               │
│  当前对话名 + 切换按钮               │
├─────────────────────────────────────┤
│ 消息流（可滚动）                     │
│  - 真人消息（incoming）               │
│  - 化身消息（outgoing）                │
│  - 系统消息 / 错误                    │
├─────────────────────────────────────┤
│ 输入区                               │
│  textarea + 命令自动补全             │
│  [发送] [清空] [新对话]              │
└─────────────────────────────────────┘
```

### 10.3 消息流设计

- 单列 vertical scroller
- 消息气泡：左 = 真人（incoming），右 = 化身（outgoing）
- @slug mention 高亮
- 系统消息用灰色 thin 文本行（"Component scheduled at ..."）

### 10.4 输入区

- textarea（单行变高模式，⌘Enter 提交）
- 实时解析 `@slug /cmd` 段落化
- 目标选择器 chip（一键插入 `@current_slug`）
- 命令自动补全：`/` 弹下拉
- 发送按钮 + loading 状态
- 「新对话」按钮清空当前对话（保留前 N 条到历史）

### 10.5 Composer 全屏

- 触发：右上角全屏图标 或 Cmd+Shift+F
- 视觉：整个 viewport 都显示 Composer，sidebar / 主画布 / status bar 全部隐藏（z-index 高于所有）
- 退出：Esc 或右上角还原按钮
- 全屏时 Composer 显示聊天列表（左栏）+ 当前对话（中栏）+ 输入区（右栏），3 栏布局

### 10.6 跨化身对话

- 一次 Composer 可同时派给多个 `@slug`
- 每个 `@slug` 一个 chat channel（input 段落化）
- 列表显示每个 `@slug` 的未读红点 + 最新一条预览

### 10.7 与节点跳转联动

点击主画布上的某个化身节点 → 节点浮窗里有「在 Composer 里聊」按钮 → 在 Composer 输入区预填 `@<that slug>`，自动 focus。

---

## §11 Topology Dashboard（主画布默认 tab）

### 11.1 路由 / 进入

- 进入 `/workspaces/:id` → 默认渲染主画布为 tab"拓扑"
- 全屏打开：`Cmd+Shift+T` 或 sidebar 拓扑按钮长按 → 进入全屏 dashboard 模式

### 11.2 主画布布局

```
┌─────────────────────────────────────────────────────┐
│ Toolbar：模式切换 [选择 V] [连接 C] [移动 M]   Zoom ▾ │
├─────────────────────────────────────────────────────┤
│                                                     │
│      ╭─◯─╮         ╭─◯─╮                          │
│      │ AI │ ───────  │ 你 │                          │
│      ╰───╯         ╰───╯                          │
│                                                     │
│      [全屏] [刷新] [清空过滤]                      │
└─────────────────────────────────────────────────────┘
```

### 11.3 节点类型 + 视觉

| 节点类型 | 形状 | 颜色 | 含义 |
|---|---|---|---|
| **AI 眷族节点** | 圆 40px | 头像圆 + 神职 chip | 当前 workspace 的 AI 智能体身份 |
| **AI 化身节点** | 嵌套小圆 | 继承 loop_status glow | 眷族派生的运行态（心智能状态） |
| **真人契印节点** | 圆 40px | 纯灰底（slate-200） | 当前 workspace 的真人操作员 |
| **主脑节点** | 大六边形 | 紫红渐变 | Workspace 中央主脑（4 脑区聚合） |

**glow 颜色对应**：
- running = #10b981 / 强
- idle = #eab308 / 中
- paused = #94a3b8 / 弱
- interrupted = #ef4444 / 中
- completed = #3b82f6 / 低
- failed = #dc2626 / 强

**节点 outdated 状态徽章**（当 `Instance.active_hash != Entity.promotion_migration_hash` 时，详见 §13.6.5）：
- 化身节点外圈加 2px 黄色 dashed border
- 节点右上角加小角标：`outdated`（黄色 chip）
- glow halo 保持原 loop_status 颜色（不混）

### 11.4 节点 hover tooltip

| 节点类型 | tooltip 内容 |
|---|---|
| AI 眷族 | 眷族名 + slug + rank + 神职 chip + 已绑深海基因数 + Entity.migration_hash（截断 8 字符）+ "进入记忆" 链接 |
| AI 化身 | 眷族 → 化身 ID + loop_status + 续命次数 + 心智状态 + **outdated?**（是 → 提示「重启以更新到最新 hash」+ 「重启此化身」按钮） + "查看详情" 链接 |
| 真人契印 | 用户名 + 邮箱 + 觉醒基因 + 加入时间 |
| 主脑 | 4 脑区状态聚合（穹窿 / 额叶 / 脑干 / 小脑）+ 主脑健康度 + "进入主脑" 链接 |

### 11.5 节点 click 浮窗

**触发**：单击节点 → 主画布整体 blur + 暗化 30% → 节点浮窗出现

**浮窗结构**：

| 节点 | 浮窗内容 |
|---|---|
| AI 眷族 | 眷族详情（同 §8.5 浮窗）+ 「进入记忆详情」/「绑定深海基因」/「软删除」/「跳到 Topology 上的位置」按钮 |
| AI 化身 | 化身详情（loop_status 5 control buttons + 当前记忆数 + 所属眷族）+ 「跳到记忆详情」/「回 Topology」 |
| 真人契印 | 用户详情 + 觉醒基因 + 「查看用户」/「移除契印」 |
| 主脑 | 4 脑区当前状态卡片 + 「进入穹窿 / 额叶 / 脑干 / 小脑」按钮 |

**关闭**：浮窗外点击 / Esc / 浮窗右上 × / "回到 Topology" 按钮。

### 11.6 节点 dblclick → 持久化 tab

**触发**：双击节点 → 在主画布 tab 栏新增一个 tab（如"化身 #abc123"），主画布切换到该 tab

**新 tab 内容**（取决于节点类型）：
- AI 化身的详情页（旧 §9 化身详情页内容）
- AI 眷族的记忆聚合页（旧 §13 学习页内容）
- 真人契印详情页
- 主脑 4 脑区的某个子视图

**关闭**：tab × 按钮

**与浮窗的差别**：
- 浮窗 = 临时查看（关掉就没了）
- dblclick tab = 持续化（用户切换其他 tab 后再回来仍在）

### 11.7 三模式交互（v / c / m）

| 模式 | 快捷键 | 行为 |
|---|---|---|
| 选择 (Select) | `V` | hover tooltip / click 浮窗 / dblclick tab |
| 连接 (Connect) | `C` | 点源节点 → 高亮连接态 → 点目标节点 → 创建通道 |
| 移动 (Move) | `M` | 拖拽节点改 posx/posy，松手 PATCH |

### 11.8 实时刷新

- 每 2 秒拉 `/workspaces/:wid/live-status` 更新节点 glow
- 每 5 秒拉 `/events?type_prefix=messaging.&since=5s_ago` 触发通道粒子动画

### 11.9 Navigator 跳转（点击节点关联对象 → 信息页）

按用户的明确要求：

| 节点 / 元素 | 点击行为 | 跳转目标 |
|---|---|---|
| **眷族节点 / 卡片** | 单击浮窗的"神职 chip" / 详情 | 跳 `/namespaces?tab=base-classes&focus=<slug>` （神职市场该 BaseClass 详情页） |
| **化身节点** | 浮窗或 tab 中点 "查看记忆" / "进入眷族" | workspace dashboard 切到「记忆」tab + focus 到该眷族记忆 |
| **化身节点** | 浮窗 "跳到所在 workspace" | 跳 `/workspaces/<wid>?fullscreen=<iid>` （workspace dashboard + 全屏打开该化身） |
| **真人契印节点** | 浮窗 "查看用户" | 跳 `/contracts?focus=<uid>` 全局契印详情 |
| **Workspace 节点 / Link** | (rare) | 跳该 workspace dashboard 全屏模式 |

**实现**：所有跳转用 `react-router-dom` `<Link>` 或 `useNavigate()`，保留 dashboard 上下文（焦点状态）。

---

## §11.U 拓扑 Dashboard UI 详写（start-work 落地用）

### 11.U.1 节点渲染系统（SVG）

**ViewBox**：`-1000 -1000 2000 2000`（user coords），`preserveAspectRatio="xMidYMid meet"`

**基础节点圆**：
- 半径：40px（core）、52px（halo 外环）
- Core 填充：`#e2e8f0`（AI 节点默认灰底） / `#3b82f6`（AI 化身上的蓝底）
- Core 描边：2px + `node.glowColor` + opacity 按 `intensityStrokeOpacity`（0.4-1）

**节点类型映射到 SVG 渲染**：

| 节点类型 | 形状 | 尺寸 | 内部图标 | 外圈（halo） | Core 颜色 |
|---|---|---|---|---|---|
| AI 眷族 | 圆 | 40px | `Bot` (20px, lucide) | glow 按 loop_status 颜色 | `#e2e8f0` |
| AI 化身 | 嵌套双圆 | external=52px, core=40px | `Cpu` (20px) | glow 动态 + outdated-dashed 叠加 | `#3b82f6` |
| 真人契印 | 圆 | 40px | `User` (20px) | 无 halo | `#e2e8f0` |
| 主脑节点 | 大六边形 | 60×52 | `Brain` (24px) | 紫红渐变 glow | `#7c3aed`→`#eab308` |

**Glow 外环（halo）**：
```tsx
{haloOpacity > 0 ? (
  <circle r={52} stroke={node.glowColor} strokeOpacity={haloOpacity}
    strokeWidth={8} filter="url(#topology-glow-blur)" />
) : null}
```

Glow filter：`<feGaussianBlur stdDeviation="4" />`（defined in `<defs>` via `TopologyGlowDefs` component）。

**Outdated 叠加**（当 `Instance.active_hash != Entity.promotion_migration_hash` 时）：
```tsx
{node.outdated ? (
  <circle r={58} stroke="#eab308" strokeWidth={2} strokeDasharray="6 3" fill="none" />
  { /* 右上角黄色角标 */ }
  <foreignObject x={18} y={-46} width={28} height={16}>
    <span class="text-xs text-white bg-amber-500 rounded px-1.5 py-0.5 font-mono">outd.</span>
  </foreignObject>
) : null}
```

### 11.U.2 节点 hover tooltip（3 档逐层展开）

**触发**：鼠标悬停 ≥ 500ms

**tooltip 规格**：
- 位置：节点中心上方偏移 60px，白底 + 灰边
- 宽度：自动 fit content（min 160px, max 320px）
- 3 层信息（按行数递增）：

| 层 | 显示 | 所有类型 | 特殊情况 |
|---|---|---|---|
| **L1** 基本 | label + loop_status badge + slug（mono） | ✓ | |
| **L2** 扩展 | 续命次数 / 最后 checkpoint / outdated?（是 → 红色提示） | AI 化身 only |
| **L3** 操作 | "查看详情" / "在 Composer 里聊" / "重启以更新" / "移除契印" 等 1-2 个操作链接 | 按类型 | L3 按钮仅在非 outdated 正常状态下活跃 |

**L3 按钮列表（按节点类型）**：
| 节点类型 | L3 操作 |
|---|---|
| AI 化身 | 「查看详情」（→ click 浮窗） / 「在 Composer 里聊」/ 「重启以更新」（仅 outdated） |
| AI 眷族 | 「进入记忆」 |
| 真人契印 | 「查看用户信息」 / 「移除契印」（仅超管） |
| 主脑 | 「进入主脑」 / 「进入穹窿 / 额叶 / 脑干」 |

**实现**：使用 SVG `<foreignObject>` 内嵌 HTML（方便样式复用 + 键盘可达）。

### 11.U.3 click 浮窗（模态浮层）

**触发**：单击节点（非 dblclick 计时器内）

**动画**：
- 主画布 (`.topology-canvas`) 添加 CSS filter `blur(8px)` + opacity `30%`，duration 200ms ease-out
- 浮窗从节点中心位置 scale(0) → scale(1) 放大弹出（300ms spring）
- 关闭：反向动画 scale(1)→scale(0) + blur/opacity 恢复

**浮窗尺寸**：920×640（desktop / tablet 可缩放），移动端全屏 sheet

**浮窗结构**（取决于节点类型）：
- **AI 化身浮窗**：化身详情（compact）+ 3 个操作 card（5 控制 button / 当前记忆 info / outdated? → 重启CTA）+ "回 Topology"
- **AI 眷族浮窗**：同 §13.2.U.2 眷族详情浮窗（7 tab 完整）
- **真人契印浮窗**：用户信息 + 觉醒基因 chip + 操作（「查看用户」→ 全局契印详情 / 「移除契印」）
- **主脑浮窗**：4 脑区状态卡片（small each）+ "进入主脑"

**关闭**：
- 浮窗外任意点击 / Esc / 右上 × / "回到 Topology" 按钮
- 关闭后 node 回到"未选中"状态（淡出选中 halo）

**焦点管理**：浮窗 trap 焦点（Tab 在浮窗内循环），Esc 关闭并恢复焦点到该节点 `g[data-topology-node]`。

### 11.U.4 dblclick → 持久化 tab

**触发**：双击节点（dblclick 间隔 300ms 去重）

**Tab 注册**：`tabStore.addTab({ id: \`instance-\${iid}\`, label: node.label, content: <InstanceDetailPanel /> })`

**渲染**：
- 主画布 tab 栏 header 新增 tab 项（右侧 `×` 关闭）
- 渲染内容的组件：`<InstanceDetailPanel instanceId={...} />`（复用 §9 化身详情页的内容，但去掉 header + 面包屑导航——全部内容用 dashboard 主画布区域）
- 内容加载时显示 skeleton + "Loading instance detail..."
- 内容错误时显示 error banner + retry

**Tab 关闭**：`×` 按钮 → 从 tabStore 移除该 tab，自动回到上一个活跃 tab（默认为 topology tab）

**持久化**：即使用户切到其他 workspace / namespace，只要 session 不关，tab 一直保留（`sessionStorage` 或 `tabStore` 持活）

**深度链接**：`/workspaces/:id?tab=instance-xxx` 可直接打开带该 tab 的 dashboard

### 11.U.5 三模式交互 UI 详写

**Toolbar 渲染**（固定在主画布左上角）：
3 个 `<button role="radio">` 的 pill 样式 toolbar：
```
┌─────────────────────┐
│ [选择 V] [连接 C] [移动 M]  │
└─────────────────────┘
```

- 当前 mode 高亮：`bg-blue-600 text-white`
- 其他模式：`bg-white text-slate-600 border border-slate-200`
- 不可重复选中同一个 mode
- keyboard shortcut 实时切换（V / C / M）

**模式切换时**：
- 如果是 `connect` → 取消任何`move` drag 状态
- 如果是 `select` → 清除任何 pending 连接
- cursor 跟随模式：`cursor-pointer`(select) / `cursor-crosshair`(connect) / `cursor-move`(move)

**连接模式 创建走廊** (
):
1. 用户在 `connect` 模式点源节点 → 节点外圈变橙色 dashed border + 顶部 status bar 显示 "点击目标节点"
2. 用户点目标节点 → POST `/api/v1/central-hubs/{wid}/passage`（之前 `/messaging/corridors`） → 新 edge 出现在 canvas
3. 成功 → 源节点恢复正常 + green toast "通道已建立"
4. 失败 → 源节点回退橙色 + red toast "通道创建失败: <error>"
5. 取消：点空白 / Esc

### 11.U.6 节点拖拽（move 模式）UI

- 拖拽中：节点跟随鼠标（实时渲染，无操作节流）
- **不持久化**：松手时再 PATCH `/api/v1/messaging/memberships/:mid`（拖拽过程不产生请求）
- 405 / 409（pos already used）→ node revert 到拖拽前位置 + toast "坐标 (x, y) 已被占用"

### 11.U.7 实时刷新系统

**2s 心跳（live status）**：
```ts
// GET /api/v1/central-hubs/{wid}/live-status
// returns: LiveStatusItem[]
{
  "membership_id": "uuid-xxx",
  "posx": 42,
  "posy": 99,
  "glow": { "color": "#10b981", "intensity": "strong" },
  "outdated": false,
  "active_hash": "sha256:..."
}
```

Scheduler: `useEffect` 2s interval + cleanup。Response 更新每个节点的 `glow` + `outdated` state。

**5s 消息激活刷新** (particle animation)：
```ts
// GET /api/v1/events?type_prefix=messaging.&since=5s_ago&limit=20
```
找到 `messaging.message_sent` event → 取 `payload.corridor_id` → 往 `activeCorridors` Map 里 set(corridorId, Date.now() + 1000) → `<animateMotion>` 被触发（1s 粒子动画）。

**过期清理**：每 200ms tick 清理 `activeCorridors` 中 expired 的键。

### 11.U.8 边界与错误（拓扑 canvas）

- Canvas 空态（0 节点）：显示 "还没有契印或化身——召唤第一个眷族" 文字 CTA
- 画布加载失败（API error）："加载拓扑失败" error banner + retry
- Outdated 节点的 restart 按钮触发 workflow：
  1. 弹 confirm modal："重启 Instance #abc？当前 loop 将停止，pod 重新创建，新能力自动装入"
  2. 确认 → POST `/api/v1/instances/:iid/restart` → 2s poll live-status 检查新 hash → 成功 green toast / 失败 red toast
- 连接模式未完成 target：取消（点空白 / Esc）
- drag 出边界（>1000 / <-1000）：node 弹回内缩放

### 11.U.9 Keyboard 快捷键拓扑侧

| 快捷键 | 模式 | 行为 |
|---|---|---|
| `V` / `C` / `M` | 全局 | 切换 select / connect / move 模式 |
| `Esc` | 全局 | 清 pending connection / drag / 关闭浮窗 |
| `Cmd+Z` | 全局 | undo last node move（v1 可选） |
| `↑ ↓ ← →` | move | 微调选中节点位置（±10px per keypress） |
| `Enter` | select | 触发 click（打开浮窗） |

---

## §12 调试页（namespace tab 内 + workspace 内可访问）

### 12.1 路由

- `/namespaces?tab=debug` — namespace 调试
- workspace 内 status bar 的 `Bug` 图标 → 跳 namespace 调试
- 双击：sidebar 调试图标直接打开

### 12.2 详细布局

详细规格同 P15c 已实现版本（filter bar + 事件表格 + 6 type-prefix quick picks + 3 时间范围 quick picks + 重置 + 导出 JSON）。v1 不重构这部分。

---

## §13 记忆 + 眷族管理 + 神职市场（重构后的命名）

> **重命名**：原 §13 "学习页 + 蒸馏 UI" 改名《记忆 + 眷族管理 + 神职市场》。**记忆**作为章节主名（用户原话："学习这边改成叫记忆吧"）。

### 13.1 章节分段

| 子节 | 覆盖范围 |
|---|---|
| **§13.1 记忆管理（workspace dashboard tab "记忆"）** | Workspace dashboard 主画布 tab 之 "记忆" — 眷族记忆聚合 + 单眷族记忆详情 |
| **§13.2 眷族配置（namespace tab "眷族"）** | 全局眷族属性管理 + 深海基因绑定 + 炼化触发 |
| **§13.3 神职市场（namespace tab "神职"）** | §8.3 详 |

### 13.1 记忆管理

#### 13.1.1 记忆 tab（workspace dashboard 主画布）

**进入**：`/workspaces/:id` 主画布切到"记忆"tab

**结构**：
- 顶部 stats：当前 workspace 眷族数 / 累计 Memory 条目数 / 待晋升候选数（≥N 条经验的眷族）
- 主区：眷族聚合列表（按眷族 card grid）
- 每张眷族卡内容：
  - 眷族显示名 + slug + 神职 chip + rank badge
  - 4 个 kind 记忆计数小卡片（经验 / 教训 / 决策 / 问题）
  - 操作：「查看记忆详情」/「晋升」/「炼化」（移动到 namespace 级"眷族"操作）

#### 13.1.2 单眷族记忆详情（浮窗 / dblclick tab）

**进入**：
- 从记忆 tab 卡片点击 → 主画布浮窗
- 从拓扑节点浮窗 → dblclick → 持久化 tab
- URL：`/workspaces/:id?focus=memory&entity=:eid`

**结构**：
- 顶部：眷族显示名 + 神职 + rank
- 左：Memory 汇总（4 kind count + 5 条最近 lessons）
- 右：蒸馏表单（晋升 / 炼化 按钮组）
- 顶部 stats：累计 memory 数量 + 上次晋升 / 上次炼化时间 + 心跳

**蒸馏表单**：
- 晋升按钮（绿色）：触发 Instance → Entity 原地 Memory 回写
- 炼化按钮（紫红）：触发 Entity → BaseClass 蒸馏（需填目标 slug）
- 完成后弹 Result Modal（新 BaseClass 预览 + chain → §13.3 神职详情页）

#### 13.1.3 Memory 入口与生命周期

- v1 Memory 来源：
  - 化身运行时自动写（loop 关键事件 → kind=lesson / decision / problem）
  - 真人手动通过 Composer 注入（"@[slug] /remember ..."）
  - 深海基因携带（v1 部分 gene 预置）

- 晋升触发：用户手动触发（v1）；未来可自动 trigger（基于记忆数阈值）
- 炼化触发：用户手动触发（v1）

### 13.2 眷族配置（namespace tab "眷族"）

> 见 §8.5「眷族 tab」。本节补充眷族配置的具体操作。

#### 13.2.1 眷族基本属性

- name / slug / display_name / description
- rank（创建后冻结）
- BaseClass（创建后冻结，不可修改）
- 创建时间 / 创建者

#### 13.2.2 深海基因绑定

- 显示已绑定的深海基因列表（按 source 分组：from BaseClass / 额外添加）
- 「+ 添加额外基因」按钮 → 弹模态选择深海基因（来自 `/base-classes` 列表过滤出基因类型）
- 单条基因「移除」按钮（仅额外添加的能删，from BaseClass 的不可删）

> 详细：§14b 深海基因管理。

#### 13.2.3 炼化触发入口（在眷族配置页）

- 「炼化成新神职」按钮（需 `can_transmute_entity`）
- 弹模态：填目标 slug → POST 蒸馏 → 跳到新 BaseClass 详情页

#### 13.2.4 Navigator 跳转（点击关联对象）

| 关联对象 | 点击行为 | 跳转目标 |
|---|---|---|
| 眷族卡上的 **神职 chip** | 单击 | 跳 `/namespaces?tab=base-classes&focus=<slug>` （神职详情） |
| 眷族卡上的 **化身节点** | 单击 | 跳 `/workspaces/<wid>?fullscreen=<iid>` （workspace dashboard 全屏该化身） |
| 眷族详情浮窗的 **workspace 标签** | 单击 | 跳 `/workspaces/<wid>?focus=memory&entity=<eid>` （同一 workspace dashboard 记忆 tab 定位到此眷族） |

### 13.3 神职市场（namespace tab "神职"）

> 见 §8.3 神职 tab。本节只补充神职**详细属性页**的 UI 规格。

#### 13.3.1 神职详情浮窗（点击神职卡片触发）

- 大 display name + slug
- 完整职能说明（prose 段落，2-4 段）
- 命令全集（不限 3 个，hover tooltip）
- Provider 默认 + override 字段
- prompt 前 200 字预览
- 依赖深海基因列表
- 来源 / 版本
- CTA：「基于此神职召唤眷族」→ §6 引导 Step 1 预选此 BaseClass

#### 13.3.2 双击神职卡片 → 神职详情全屏页

URL：`/base-classes/:slug`

- 详情浮窗全部内容
- 多段描述长文展开
- 实时统计：从该神职派生的眷族列表（跨 workspace 全局）
- /memory：该神职派生眷族的记忆聚合（按 workspace 分组）

### 13.4 蒸馏 2 动作（操作层）

> **完整数据流语义**（4 级跳 + API 体 / 副作用 / 边界）见 **§13.6**。本节只讲**用户操作层**——按钮放哪、什么时候点。

#### 晋升 (promote) — 见 §13.6.3 完整定义

**触发位置（用户操作）**：
- workspace dashboard 记忆 tab 眷族卡（在该眷族所有 Instance 都停止 / 已无 running 时）
- namespace tab 眷族详情浮窗 → 「炼化」tab → 晋升 card

**API**：`POST /api/v1/learning/entities/:eid/distill?action=promote`

#### 炼化 (transmute) — 见 §13.6.4 完整定义

**触发位置（用户操作）**：
- namespace tab 眷族详情浮窗 → 「炼化」tab → 炼化 card
- workspace dashboard 记忆 tab 卡片上（带跨 workspace 提醒）— 跳到 namespace 级执行

**API**：`POST /api/v1/learning/entities/:eid/distill?action=transmute`

> **关键区分**：晋升 = Entity 内部升级（同 workspace 内变强）。炼化 = 跨 workspace 资产生产（产生新神职模板）。**用户看按钮时**：晋升带绿色 = "升级这个眷族"，炼化带紫红 = "蒸馏成新神职"。

### 13.5 与基因（深海基因）的关系

- 蒸馏动作产生的是 **BaseClass**，**不是**深海基因
- BaseClass 定义 AI 的 prompt + commands + provider config
- 深海基因定义 AI 的 capabilities（skills / tools / mcps / lsps）
- 新 BaseClass 可以**引用**已存在的深海基因作为默认安装包（在 §13.3 详情页可以勾选）
- 蒸馏产物 ≠ 深海基因

---

## §13.6 能力生命周期模型：Memory → Capability → Gene → BaseClass（4 级跳）

> **核心澄清**：用户原话反馈"晋升和炼化做了什么？一个是不是能力系统保存？另一个是记忆？记忆回收后应该变成能力？能力组合成基因？这是一套三级跳"。
>
> 这是 Cocoa 的**核心数据流**。所有蒸馏动作的本质都从这条链来。本节给完整定义，避免 §13.1-§13.5 与 §13.UX 之间的歧义。

### 13.6.1 4 个层级（从低到高）

| 层级 | 名称 | 存储位置 | 类型 | 描述 |
|---|---|---|---|---|
| **L1** | **Memory**（记忆沉淀） | `Memory` 表 / `Entity.memory_entries` | `experience / lesson / decision / problem` | 化身跑过的事、踩过的坑、做过的决策。是**事实记录**，无能力性 |
| **L2** | **Capability**（能力） | `Entity.capabilities[]` 字段（运行时复制到 `Instance.capabilities`） | `skill / tool / mcp / lsp` | 由 Memory 蒸馏出的"能做某事"的单元。是**可执行的能力** |
| **L3** | **Gene**（基因 = 能力包） | `ai_genes` 表 / `BaseClass.installed_gene_slugs[]` | 4 类（`tool-gene / meta-gene / genome / workflow-gene`）| 命名打包的能力集合。一个基因 = 多个 Capability |
| **L4** | **BaseClass**（神职 = AI 角色模板） | `base_classes` 表 | 系统级 / 自定义 | Entity 身份 + Memory + 完整能力集 + prompt 的整合体。**跨 workspace 复用** |

### 13.6.2 6 个动作的精确边界

> **核心修正**（用户原话："你回收就是 memory 转 capability 回收给当前 instance，然后同步写能力市场；你回收之后晋升，才会写 entity 否则 entity 是不做同步的"）：
>
> 之前我把"回收 + 晋升"合并成一个动作——**错的**。这是 2 个**独立**动作，必须分开看。

| # | 动作 | 名称 | 起点 | 终点 | 模型 | 边界（用户操作时会得到什么） |
|---|---|---|---|---|---|---|
| 1 | **采集** | 自动写入 | 化身 runtime 事件 | `Memory` 条目 | 自动（loop hook 监听 `EventLog`）| 用户**不可操作**，系统自动 |
| 2 | **回收** | Memory → Capability | 当前 Instance 的 1 条 / 多条 Memory 条目 | (a) Instance 私有新增 capability + (b) 同步上架 capability_market | **回收 = 单步能力沉淀**：从"经验"蒸馏出"能力"，归当前 Instance 私有 + 公开到市场 | 用户得到 1 条新 capability（Instance 用 + 市场可被引用）。**Entity 不变** |
| 3 | **装载** | Gene + Capability → Instance runtime | Capability / Gene manifest | 写入容器（skill dir / tool registry / mcp process / lsp client）| GeneInstallAdapter | 用户得到"runtime 可用" |
| 4 | **组合** | 多 Capability → 1 Gene | 多条 capability + 自命名 | 1 个新 Gene (`ai_genes` insert) | 用户操作 / 系统 auto-suggest | 用户得到"命名打包的能力集，可被多个 BaseClass 引用" |
| 5 | **晋升** | Instance cap 集 → Entity 共享层 | 当前 Instance 的全部 capability（含 BaseClass 默认 + 回收新增 + gene 装入） | Entity.capabilities 新增（add 操作，幂等 by name） + Entity.migration_hash bump | **晋升 = 单步能力共享**：把 Instance 当前能用的能力"提升"到 Entity 层，让同 Entity 其他 Instance 共享。**不写 capability_market**（这条是 Entity 内部共享，不是市场公开） | 用户得到 Entity cap 集变更。同 Entity 的其他 Instance 进入 outdated 状态（不主动重启） |
| 6 | **炼化** | Entity 完整身份 → 新 BaseClass | Entity 当前 cap 集 + Entity.prompt_regen_snapshot + 默认 god_gene 列表 | 1 个新 BaseClass record | **炼化 ≠ 晋升**。是 Entity 整体身份 → 跨 workspace 神职模板。**不**含 Memory，**不**写 capability_market（这条是公开模板，不是公开原子） | 用户得到新 BaseClass record。现有 Entity / Instance / 现有 BaseClass 绑定的 Entity **都不变** |

> **重点澄清**：
> - **回收 vs 晋升**：回收是"沉淀给当前 Instance + 上架市场"，晋升是"提升到 Entity 共享"。**不晋升，Entity 不动**。
> - **晋升 vs 炼化**：晋升是 Entity 内部共享，炼化是跨 workspace 资产生产。
> - 3 个写入位置（Entity / capability_market / 容器）的清晰分工：
>   - **回收** → Instance 私有 + capability_market（不写 Entity）
>   - **晋升** → Entity 共享（不写 capability_market）
>   - **炼化** → 新 BaseClass（不写 Entity，不写 capability_market）

### 13.6.3 回收 (reap) — Memory → Capability（单 Instance 私有 + 公开市场）

#### 13.6.3.1 核心定义

回收 = **把当前 Instance 的 Memory 条目蒸馏成 capability 原子**，归 Instance 私有 + 同步到全局能力市场。

> 这是 **Instance 视角的"自我提升"**——单一 Instance 跑出来的新能力，只有它自己用 + 全局市场可见。Entity 不知道这件事（不写 Entity）。

#### 13.6.3.2 完整效果

| 维度 | 回收前 | 回收后 |
|---|---|---|
| **Instance 私有 capabilities** | BaseClass 默认 + 之前回收的 + gene 装入的 | **新增**：本次蒸馏出的 capability 原子（add 幂等 by name） |
| **capability_market** | 之前已上架的 | **新增**：每条本次蒸馏出的 capability（如果 name 不已存在；不覆盖） |
| **Entity.capabilities** | 不变 | **不变**（Entity 不知道这件事） |
| **Entity.migration_hash** | 不变 | **不变**（不 bump） |
| **Entity.prompt_regen_snapshot** | 不变 | **不变** |
| **同 Entity 其他 Instance** | 不变 | **不变**（不知道有这条新能力） |

#### 13.6.3.3 API 形态

**Endpoint**：`POST /api/v1/learning/instances/:iid/reap`

**Body**（v1）：
```json
{
  "memory_kind_filter": ["lesson", "decision"],   // 可选，默认全选
  "max_capabilities": 10,                          // 上限保护，默认 10
  "snapshot_only": false                           // true = 预览（不写库）
}
```

**响应**：
```json
{
  "status": "ok",
  "reaped_at": "2026-07-28T...",
  "instance_id": "uuid-of-instance",
  "memory_consumed": 12,                          // 蒸馏消耗的 Memory 条数
  "capability_distilled": [
    {
      "name": "workflow-design-patterns",
      "type": "skill",
      "description": "...",
      "tags": ["auto-distilled"]
    },
    {
      "name": "data-fetching-tool",
      "type": "tool",
      "description": "...",
      "tags": ["auto-distilled"]
    }
  ],
  "capability_market_uploaded": 2,                // 新上架到能力市场的条数（0 = 全已存在）
  "instance_local_added": 2,                      // Instance 私有新增条数
  "entity_changed": false                         // 恒为 false（Entity 不知道）
}
```

#### 13.6.3.4 "刚 spawn 立刻回收"特例

| 场景 | 行为 |
|---|---|
| 刚 spawn → 立刻回收 | Instance runtime 此时**没 Memory**（Memory 还没生成）；回收结果：memory_consumed=0，capability_distilled=[]，无副作用 |

**意义**：回收是"声明此次有可蒸馏的 Memory"，无 Memory 则无变化。**Entity 永远不变**（无 Memory 蒸馏、无 cap 上架）。

#### 13.6.3.5 UI 入口（与晋升独立显示）

| 入口 | UI 形态 |
|---|---|
| 化身详情页 Header | 「回收 Memory」+「晋升到 Entity」两个**独立**按钮（不再合并） |
| workspace dashboard 记忆 tab 眷族卡 | 该眷族下每个 Instance 行：「回收」/「晋升」/「回收+晋升」三选一 |
| 眷族详情浮窗 "当前化身" tab | 每行化身 row 末尾：「回收」/「晋升」两个独立按钮 |
| namespace tab 眷族详情 | "回收+晋升"批量操作（v2 后续） |

#### 13.6.3.6 「回收+晋升」二合一按钮（推荐 UX）

虽然两个动作独立，但用户视角经常想"做了回收立刻晋升"。提供**快捷按钮**「回收+晋升」：

- 点击 → 后端先执行 reap（回收）→ 立即执行 promote（晋升），**两次 API 调用一次 button**
- 进度反馈：步骤 1 回收中（spinner）→ 步骤 2 晋升中（spinner）→ 完成 toast
- **任何一步失败** → rollback 提示（已回收的部分保留，已晋升的部分回滚到回收前状态）

### 13.6.4 晋升 (promote) — Instance cap 集 → Entity 共享层

#### 13.6.4.1 核心定义

晋升 = **把当前 Instance 的 cap 集"提升"到 Entity 共享层**。让同 Entity 的其他 Instance 共享这次的能力。

> 这是 **Entity 视角的"同步给同 Entity 其他人"**。Instance 自己不变（已经装了的 cap 还是装着的），Entity 共享层多 1 条记录。

> **重要修正**：晋升**不**写 capability_market（之前 v1 误判）——这条能力是 Entity 内部共享，不是市场公开。Entity 共享和市场公开是两个独立写入。

#### 13.6.4.2 完整效果表

| 维度 | 晋升前 | 晋升后 |
|---|---|---|
| **Entity.capabilities** | 之前的 | **新增**：本次晋升的 Instance 当前的 cap 集（add 幂等 by name） |
| **Entity.prompt_regen_snapshot** | 旧的 | **新快照**：基于 BaseClass manifest + Entity 升后 capability 集重计算 |
| **Entity.promotion_migration_hash** | 旧的 | **新 hash**（包含时间戳 + cap 集摘要 + prompt 摘要 SHA-256） |
| **Entity.Memory** | 不变 | **不变**（Memory 是事实日志） |
| **capability_market** | 不变 | **不变**（**晋升不写市场**——和市场是 2 个独立写入动作） |
| **Instance.runtime** | 用旧 hash / 旧 prompt | **不主动重启**；下次启动 / 重启时检测 hash mismatch |
| **同 Entity 其他 Instance** | 旧 hash | **outdated 状态**（不主动重启） |
| **BaseClass 关联 / rank / 身份** | 不变 | **不变** |

#### 13.6.4.3 "刚 spawn 立刻晋升"特例

| 场景 | 行为 |
|---|---|
| 刚 spawn → 立刻晋升 | Instance 当前 cap = BaseClass 默认；晋升 = 把这些默认 cap add 到 Entity.capabilities（如果已存在则幂等无 diff）；prompt_regen_snapshot 重新计算（值与初始一致）；migration_hash 仍 bump（**任何晋升都 bump hash**，即便内容无变化） |

**意义**：bump 让其他 Instance 进入 outdated 状态 → 用户看到 "promoted at <时间>" + "outdated" 徽章 → 主动决定是否批量重启 Instance → 不强行打断。

#### 13.6.4.4 API 形态

**Endpoint**：`POST /api/v1/learning/entities/:eid/promote`

**Body**（v1）：
```json
{
  "from_instance_id": "uuid-of-instance",  // 默认当前 context Instance
  "include_prompt_regen": true,             // 默认 true
  "snapshot_only": false                    // true = 预览
}
```

> 注意：晋升**不**接收 `memory_kind_filter`——晋升不消费 Memory（回收才消费 Memory）。晋升只读 Instance 当前 cap 集。

**响应**：
```json
{
  "status": "ok",
  "promoted_at": "2026-07-28T...",
  "entity_id": "uuid-of-entity",
  "entity_promotion_migration_hash": "sha256:abc...",
  "capability_promoted_count": 5,           // 写进 Entity.capabilities 的条数（含幂等去重）
  "prompt_regenerated": true,
  "new_prompt_preview": "...",
  "outdated_instances_count": 2,            // 同 Entity 其他 Instance 数（已进入 outdated）
  "capability_market_uploaded": 0          // 恒为 0（晋升不写市场）
}
```

### 13.6.5 炼化 (transmute) — Entity → 新 BaseClass（神职模板）

#### 13.6.3.1 核心定义（边界澄清）

晋升 = **把当前 Instance runtime 累积的能力系统蒸馏到所属 Entity 共享层**。

| 维度 | 写的对象 | 不写的对象 |
|---|---|---|
| **写入 `Entity.capabilities`** | ✓ 新增 capability 条目（distilled from this instance runtime） | |
| **写入 `Entity.prompt_regen_snapshot`** | ✓ 新 system_prompt 快照 | |
| **更新 `Entity.promotion_migration_hash`** | ✓ | |
| **写入 Memory** | | ✗（**Memory 不通过晋升写**——Memory 永远只是采集的事实日志，不参与能力线） |
| **影响其它 Instance** | | ✗（**不主动重启**——见 §13.6.7 migration hash 机制） |

**关键边界**：晋升**只动能力线**（capability + prompt_regen），**不动记忆线**。

> **修正之前版本**：旧版说"晋升 = Memory + Capability + prompt 三件事一起"——是错的。这次定版只动能力线。Memory 仍走独立的"采集 → 回收"流程（§13.6.7 周边）。

#### 13.6.3.2 完整效果表

| 维度 | 晋升前 | 晋升后 |
|---|---|---|
| **Entity.capabilities** | 之前累积的（如有）| **新增**本次 distilled 的 capability 条目（不删之前的） |
| **Entity.prompt_regen_snapshot** | 旧的（v0 None / 之前的快照）| **新快照**：本次晋升瞬时基于 BaseClass manifest + 新 capability 集合重新生成的 prompt 摘要 |
| **Entity.promotion_migration_hash** | 旧的 hash（如有）| **新 hash**：包含时间戳 + capability 集合摘要 + prompt 摘要 的 SHA-256 |
| **Entity.Memory** | 不变 | **不变**（Memory 是采集事实日志，不参与晋升） |
| **Entity.BaseClass 关联 / rank / 身份** | 不变 | **不变** |
| **所有 Instance.runtime** | 用旧 hash / 旧 prompt | **不主动重启**；下次 Instance 启动 / 重新部署时检测到 hash mismatch，才进入"outdated"状态 |

#### 13.6.3.3 "刚 spawn 立刻晋升"特例

| 场景 | 行为 |
|---|---|
| 刚 spawn → 立刻晋升 | Instance runtime 此时**除 BaseClass 默认能力外没新增**任何 capability；prompt 也是 BaseClass 默认。本次晋升：`Entity.capabilities` 不新增（已包含默认能力）；`Entity.prompt_regen_snapshot` 可能被重新计算（但实际值与初始一致）；`Entity.promotion_migration_hash` 仍 bump（**任何晋升都 bump hash**，即便内容无变化） |

**为什么无变化也 bump hash**：
- 用户能明确知道"我升过"（印章作用）
- 同 Entity 的其他 Instance 仍会进入 outdated 状态 → 强制显示"主动重启以更新"

#### 13.6.3.4 API 形态

**Endpoint**：`POST /api/v1/learning/entities/:eid/distill?action=promote`

**Body**（v1）：
```json
{
  "include_capability_distillation": true,        // 默认 true
  "include_prompt_regen": true,                  // 默认 true
  "snapshot_only": false                          // true = 预览（不写库，不 bump hash）
}
```

> 注意：v1 **不**包含 `memory_kind_filter`——因为晋升**不**消费 Memory。之前版本有这个字段是错的。

**响应**：
```json
{
  "status": "ok",
  "promoted_at": "2026-07-28T...",
  "instance_id": "uuid-of-promoted-instance",
  "entity_promotion_migration_hash": "sha256:abc...",   // 新 hash
  "capability_distilled": 3,                            // 本次新增到 Entity.capabilities 的 capability 数
  "prompt_regenerated": true,
  "new_prompt_preview": "..."                            // 前 200 字预览
}
```

#### 13.6.3.5 边界判定——"刚 spawn 立刻晋升"的实操

用户原话："**我刚产生一个化身 我立马把化身晋升 那其实眷族应该是无变化才对**"

完全正确。**晋升的语义是"声明此次升级"**，不是"必须有变化"：
- 无新增 capability：`Entity.capabilities` 无 diff
- 无变化 prompt：`prompt_regen_snapshot` 与 BaseClass 默认一致
- 但 `promotion_migration_hash` 永远 bump（**这是关键**——"印章"作用）

**意义**：bump 让其他 Instance 进入 outdated 状态 → 用户看到 "promoted at <时间>" + "outdated" 徽章 → 主动决定是否批量重启 Instance → 不强行打断

### 13.6.10 3 层能力市场（神职 / 能力 / 基因）— 用户原话澄清

> 用户原话反馈"**能力市场就是一个原子能力(skill/mcp/tool)的中央市场 对所有人公开 它的上一级就是基因市场 这个就是能力的打包的市场**"
>
> 这是 Cocoa 系统设计的核心简化：**3 个并列市场**，互不嵌套，是同一层级的 3 种资源类型，但**粒度递增**（原子 capability → 打包 gene → 完整模板 BaseClass）。

#### 13.6.10.1 3 层市场速览

| 级别 | 市场名称 | 内容粒度 | 路由 | 后端表 |
|---|---|---|---|---|
| **L1** | **能力市场**（原子） | 1 条 capability（skill / tool / mcp / lsp） | `/namespaces?tab=capability-market` | `capability_market` |
| **L2** | **基因市场**（打包） | 1 个 Gene = N 条 capability 的命名包 | `/namespaces?tab=genes`（现有 §14b） | `ai_genes` |
| **L3** | **神职市场**（模板） | 1 个 BaseClass = prompt + 命令 + provider + 默认能力集 + 默认基因依赖 | `/namespaces?tab=base-classes` | `base_classes` |

> 注意：3 个市场**都跨 namespace / workspace 全局可见**——不在某个 workspace 私有名下。任何真人 / 任何 AI 都可引用。

#### 13.6.10.2 能力市场详细规格

##### 13.6.10.2.1 数据库（`capability_market` 表）

```python
class CapabilityMarketEntry(BaseModel, Base):
    id: uuid
    name: str                  # e.g. "workflow-design-patterns" (kebab-case slug)
    type: enum(skill, tool, mcp, lsp)
    description: str          # 1 句话职能描述
    config_template: dict     # type-specific config（如 mcp 的连接信息占位）
    tags: list[str]           # 任意 tags 用于过滤
    created_at: datetime
    created_by_user_id: uuid  # 这个能力是谁蒸馏出来的或手创的
    created_via: enum("promote", "manual")   # 来源：晋升系统自动 / 超管手动
    source_entity_slug: str | None           # 如果是 promote 来源，记录哪个 Entity 晋升产生的
    
    deleted_at, updated_at     # 标准
```

##### 13.6.10.2.2 创建路径（2 条）

| 路径 | 触发者 | 描述 | 数据 |
|---|---|---|---|
| **A. 晋升产出** | 用户点晋升按钮 → 后端 | 晋升时新产出 capability 原子**自动**写入 capability_market | `created_via = "promote"`, `source_entity_slug = `Entity.slug |
| **B. 超管手动** | 超管 | 超管在 namespace tab 能力市场「+ 新建能力」 | `created_via = "manual"`, `source_entity_slug = null` |

##### 13.6.10.2.3 引用关系

**谁可以引用能力市场？**
1. **Entity 层**：「从能力市场添加」按钮 → 加到 `Entity.capabilities[]`（v1 暂不实现，§14b 暂用基因市场）
2. **BaseClass 层**：BaseClass.manifest.optional_capability_market_refs[] → 之后新 spawn 自动装入
3. **Gene 层**：Gene.manifest.capability_market_refs[] → 一组 capability 市场引用打包为 Gene
4. **直接 ad-hoc**（v1 不支持）：Instance runtime 直接装某 marketplace capability（不走 BaseClass / Gene）

##### 13.6.10.2.4 跨 Workspace 可见性

- v1：**全 namespace 全局可见**（一个 namespace 共享能力市场）
- v2 候选：多 namespace 之后，能力市场分 namespace 级别（你这条判断**才**实现跨 ns 共享的"G local"层级）
- v1 简化：1 个 namespace = 1 个能力市场（默认 1 个 namespace 当前状态）

##### 13.6.10.2.5 UI 规格（能力市场 tab）

**入口**：`/namespaces?tab=capability-market`

**结构**：
- 顶部过滤：type chip（all / skill / tool / mcp / lsp）+ tag 多选 + 排序（最近 / 引用最多 / 来源 newest）
- 主区：能力卡片 grid（每卡宽度约 280px）
- 每卡内容：
  - type chip + name（slug，mono）+ 1 句话职能描述
  - 「来源」chip（"从 Entity A 晋升" / "手动添加"）+ 来源创建日期
  - tags
  - 「引用次数」：被多少个 Entity / BaseClass / Gene 引用
  - 操作 row：
    - 「查看详情」→ 浮窗
    - 「+ 引用此能力」→ 下拉菜单（"加到当前选中 Entity" / "加到 BaseClass.manifest" / "加到新 Gene"）

**空态**："能力市场还空。新 Entity 晋升时产出的第一个 capability 会被自动上架。"

##### 13.6.10.2.6 详情浮窗

- 完整 description
- config_template（如果 type=mcp/lsp，看 JSON 配置示例）
- 来源链：`从 Entity A 晋升（at 2026-07-28，by User X）→ 进入能力市场 → 引用至 BaseClass B（at ...）`
- "被谁引用" 列表：所有引用此 capability 的 Entity / BaseClass / Gene（可点击跳转）
- 操作：「+ 引用到当前选中 Entity」/「分享链接」/「删除（仅创建者可删）」

#### 13.6.10.3 晋升 = 双写动作（重要修正）

按你原话："蒸馏后 [Instance] 的 capability 临时多了... 但**这个会同步到能力市场 供其他新建的眷族来引入**"

**晋升 = 2 件事**：
1. **写 Entity.capabilities**（私有化，本 Entity 看得到自己新装的能力）
2. **上架 capability 市场**（公开化，对所有人可见，可被其他 Entity 引入）

**特例**：晋升时如果"什么新能力都没有"（仅 BaseClass 默认），第 1 件事无 diff；但第 2 件事仍发生——"印章"作用。

##### 13.6.10.3.1 修订 §13.6.3 晋升定义

`POST /api/v1/learning/entities/:eid/distill?action=promote`

后端执行（v1）：
```
1. 读取当前 Instance.runtime.capabilities 增量（新装的、相对于 spawn 时的快照）
2. 对每条新 capability 原子：
   a. 写 Entity.capabilities（add 操作，幂等 by name）
   b. 写入 capability_market 表（如果该 capability.name 不已存在），filled with created_via="promote" + source_entity_slug
3. 计算新 Entity.prompt_regen_snapshot = BaseClass 默认 + 当前 capability 集合（regen 逻辑）
4. bump Entity.promotion_migration_hash
5. 写 EventLog "entity.promoted" 印痕（带新 capability list 摘要）
6. 返回新 capability 列表 + 新 hash + 新 prompt 预览
```

> 注意：**步骤 2b 是关键新增**——之前版本不写能力市场。

##### 13.6.10.3.2 UI 反馈

晋升完成后：
- 模态右侧"新上架的能力市场"章节：列出 N 条 capability，**每条带"已上架" + "已加到 Entity" 徽章**
- 链接：每条 capability 链到 `/namespaces?tab=capability-market&focus=<name>`
- 操作：「查看在能力市场的描述（draft preview）」

#### 13.6.10.4 v1 实施边界（修订 — 增 §13.6.10）

| 阶段 | 实现 | 说明 |
|---|---|---|
| **v1 必做** | 动作 5 晋升（双写 Entity + 能力市场）| 同步上架 capability_market 表 |
| **v1 必做** | 动作 6 炼化 | 写新 BaseClass（仅能力系统），**不**含 Memory，**不**影响现有 Entity |
| **v1 必做** | Entity.migration_hash 字段 + Instance outdated 检测 | 不主动重启；提供 UI 重启入口 |
| **v1 必做** | 批量重启 CTA（workspace 契印 tab）| 同 §13.6.5 |
| **v1 必做** | 拓扑节点显示 outdated 徽章 | 同 §13.6.5 |
| **v1 必做** | namespace tab 多 1 个「能力市场」| capability-market tab |
| **v1 必做** | Entity-层「从能力市场添加 capability」按钮（仅手动）| v1 不实现自动根据 Gene 推 capability（避免循环） |
| **v1 可选** | BaseClass.manifest.optional_capability_market_refs[] | v1 暂不支持 BaseClass 直接引用 marketplace；走 gene 包一下 |
| **v2 后续** | Gene 蒸馏自动建议（当 capability 在 2+ workspace 被用）| v1 不实现 |
| **v2 后续** | 能力市场分级（多 namespace 之后）| v2 才需要 |

**v1 PRD 落地建议**：
- 晋升按钮按下 → 后端实际执行「Instance runtime 新 capability → 写 Entity.capabilities + 写 capability_market + bump migration hash」
- 炼化按钮按下 → 后端执行「Entity 当前 capability → 新 BaseClass（不含 Memory，不写能力市场 — capability_market 的写只走晋升）」
- 用户不直接操作能力市场创建（除非是超管手动）

---

## §13.UX UI 详写（start-work 落地用）

> 本节是"展开写"——上面 §13.1-§13.5 是**概念**，本节是**实现规格**。任何 §13.X 引用可以回链此处查具体怎么落地。

### 13.2.U 眷族详情浮窗 / 详情页完整 UI 规格

#### 13.2.U.1 入口与打开方式

| 入口 | 触发 | 行为 |
|---|---|---|
| namespace tab 眷族卡片单击 | 主画布 blur + 暗化 | 弹出浮窗，不离 tab |
| namespace tab 眷族卡片双击 | 主画布 blur + 暗化 + 全屏 | 进入 `/entities/:eid` 详情页（无 sidebar / status bar） |
| workspace dashboard 记忆 tab 眷族卡片单击 | 同上模糊 | 打开眷族记忆版（见 §13.1.2.U） |
| workspace 拓扑 / 记忆 tab dblclick 眷族节点 | 持久化 tab | 打开 tab 内容 = 眷族详情 |

#### 13.2.U.2 浮窗整体布局

```
┌─────────────────────────────────────────────────────────────────┐
│ ◆ 某某眷族（slug: mi-xi-you-zi）                              ✕ │
├─────────────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────┐ ┌──────────────────────────┐   │
│ │ HEADER 头                      │ │ Meta 侧栏               │   │
│ │ - display name (H2, 可编辑)    │ │ - slug (mono, 可编辑)    │   │
│ │ - rank badge (浅识/深潜, 冻结) │ │ - description (textarea)│   │
│ │ - BaseClass chip (chip, 冻结) │ │ - BaseClass (display only) │   │
│ │ - "v 1.0 / @作者 / 创建时间"  │ │ - creator (真人 用户)     │   │
│ │ [保存]  [× 取消]  [⋯ 更多]    │ │ - workspace (chip, 关联)│   │
│ └──────────────────────────────┘ │ - rank (display only)    │   │
│                                  │ - AI rank since (日期) │   │
│                                  └──────────────────────────┘   │
│                                                                 │
│ Tabs:  [基本属性] [能力系统] [深海基因] [当前化身] [炼化]      │
│                                                                 │
│ TAB CONTENT (depends on selected tab)                            │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ Footer: [查看所绑 Workspace 记忆] [在拓扑中找到此 Node]         │
└─────────────────────────────────────────────────────────────────┘
```

浮窗尺寸：默认 920×640px，可拖右下角缩放（min 640×480，max 全屏）。移动端全屏 sheet。

#### 13.2.U.3 基本属性 tab（默认 tab）

这是浮窗打开时默认展示的 tab。

**字段**（详见下表）+ 保存按钮 + 操作反馈 + 关联对象可点击跳走。

| 字段 | UI 类型 | 可编辑 | 验证 | 反馈 |
|---|---|---|---|---|
| display_name | text input | ✓ | 必填，1-32 字符，去重（同 workspace） | 实时：重复 → 红框 + 文案"该 workspace 已有同名眷族"|
| slug | text input (mono) | ✓ | 必填，匹配 `/^[a-z][a-z0-9-]*$/`，去重 | 实时：违反 → 红框 + 文案"slug 必须以小写字母开头，仅含小写字母/数字/连字符" |
| description | textarea (4 行) | ✓ | 可空，最多 500 字符 | 字数计数器 bottom-right |
| BaseClass | chip (display-only) | ✗ | n/a | 鼠标悬停 tooltip 显示 BaseClass 完整描述；单击 chip → 跳转 `/namespaces?tab=base-classes&focus=<slug>` |
| rank | chip (display-only, frozen) | ✗ | 冻结不可改 | 鼠标悬停解释 tooltip "创建时定，冻结不可改" |
| creator | chip (display-only) | ✗ | n/a | 悬停显示创建者邮箱 + 注册时间 |
| workspace | chip (display-only) | ✗ | n/a | 单击 → workspace dashboard `/workspaces/:id?focus=memory&entity=:eid`（同 workspace 记忆 tab） |
| created_at | text (display-only) | ✗ | n/a | n/a |

**表单 dirty 状态**：用户改动任意字段后右上角显示橙色「未保存」徽章。点击"保存" → POST `/api/v1/entities/:eid` with If-Match ETag → 成功后绿色 toast "已保存"+ 徽章消失；如果 ETag 不匹配（其他人已改过）→ 红色 toast "该眷族已被其他人修改，请刷新"+ 提供「重新加载」按钮。

**"更多"菜单**（`⋯`）：
- 「查看历史修改」→ 时间线 view（EventLog 按 entity.* 过滤，列出所有变更）
- 「软删除」（仅 `can_summon_entity`）→ 弹确认 modal："软删除 [name]？30 天内可恢复" → 成功后 toast "已软删除"+ 关闭浮窗

#### 13.2.U.4 能力系统 tab

展示该 Entity 当前已装/绑定的 capability 集（与深海基因 tab 略有重复，但视角不同）：

**视图模式**（顶部 switcher）：「Group by type（默认）/ Group by source / All flat」

**Group by type 视图**：4 个分组（`skill` / `tool` / `mcp` / `lsp`），每个分组折叠 / 展开：

```
能力系统 (Group by type)                             [刷新]  [管理深海基因 →]
▼ skill (3)
  - workflow-design-patterns    v0.1.2     from BaseClass
  - code-review-checklist       v0.0.1     from BaseClass
  - planted-skill-1             v1.0       额外添加 →  ([移除])
▶ tool (3)
▶ mcp (2)
▶ lsp (2)
```

每行显示：
- capability name
- 版本（vX.Y.Z，hover 显示 changelog tooltip，v1 占位）
- 来源 chip：`from BaseClass`（橙色，可点 chip 跳 BaseClass 详情）/ `额外添加`（蓝色，可移除）
- 操作按钮：`[移除]`（仅额外添加的来源有，蓝色 hover 边框）
- "管理深海基因 →" 按钮（在右上角）→ 切到深海基因 tab

**空态**："该眷族还没装任何 capability — 检查 BaseClass 是否正确加载，或在「深海基因」tab 添加额外"

**Group by source 视图**：分 2 组（`from BaseClass` / `额外添加`），每组按 type 二次展开。

**All flat 视图**：表格 — name / type / version / source / operation。

**来源 chip 跳转**：点击 chip → 跳 BaseClass 详情（`from BaseClass`）或深海基因详情（`额外添加`，v1 不实现深海基因详情页时降级到深海基因列表）。

**移除 capability 流程**（`can_manage_ai_genes`）：
1. 单条「移除」按钮 → 弹确认 modal "从 [Entity name] 移除 [capability name]？新 spawn 的 Instance 不会再装，新装需要重新添加。"
2. 确认 → POST `/api/v1/entities/:eid/capabilities/:cap_id` DELETE → 成功后立即从 list 移除（乐观更新）+ 绿色 toast "已移除"。**已运行 Instance 不受影响**（这与 §2.2.4 "深海基因变更只对新建 Instance 生效" 保持一致）

**「刷新」**按钮：手动拉最新；显示 `last_sync_at` 时间戳（hover 显示完整 sync metadata）

#### 13.2.U.5 深海基因 tab

**入口**：namespace tab 眷族详情的"深海基因" tab，承接 §14b 深海基因管理

**结构**：
- 上半：当前绑定列表（按 source 分组：`from BaseClass` / `额外添加`）
  - 每行：基因名（slug） + kind chip（tool/meta/genome/workflow）+ tags + "移至 BaseClass"或"移除"操作
  - `from BaseClass` 的基因 + 锁定图标（不可移除，只能去 BaseClass 那边改）
- 下半：「+ 添加额外基因」按钮 → 弹模态
  - 模态：上为基因 grid（与 §14b 同样的列表）+ 类型过滤 + tag 过滤 + 选中预览
  - 选中后底部显示"会添加到 Entity 的额外基因列表，下次 spawn Instance 生效"

**「移除」风险确认 modal**：
"从 [Entity name] 移除 [gene name]？注意：已运行的 Instance 不受影响（要重启才生效）。下次 spawn 不会再装。"

确认 → DELETE → 移除列表 → toast

#### 13.2.U.6 当前化身 tab

**结构**：表格 + 顶部 stats（化身总数 + running / idle / failed 计数 + 整体 health badge）

**每行字段**：

| 列 | 内容 |
|---|---|
| 化身 ID（前 8 位）+ 完整 ID（hover 复制） | 单击 → `/workspaces/:wid?fullscreen=:iid`（workspace dashboard 全屏该化身） |
| loop_status badge | glow halo 圆色 8px + 文字（小）：running/idle/paused/interrupted/completed/failed |
| 续命次数 | `n`（text，hover 显示 wave 数） |
| K8s pod | pod 名称前 32 字符（hover 显示全 + 节点名 + 启动时间） |
| spawn 时间 | `x 分钟前` 格式 |
| 上次活跃 | `x 秒前`（实时更新） |
| 操作 | `跳到 workspace` / `查看记忆` / `回收`（需 `can_interrupt_instance`） |

**排序**：默认按 loop_status 优先级（failed > interrupted > paused > running > idle > completed），同状态内按 spawn 时间倒序。

**搜索 + 过滤栏**：
- 顶部 search box（输入 loop_status / pod / id 模糊搜索）
- 左侧或顶部可展开过滤：`[loop_status 选择]`、`[only-failed]` toggle、`[only-running]` toggle

**空态**："该眷族还没有 spawn 任何 Instance" + CTA「立即 Spawn 一个」→ 弹模态选择 InstanceProviderConfig 后 POST `/api/v1/instances`。

**「回收」操作**：
- 单条按钮 → 弹确认 modal "回收 Instance [id]？将停止 loop 并删除 pod。Memory 已写入眷族不会被回收。"
- 确认 → POST `DELETE /api/v1/instances/:iid` → 成功后立即从表移除 + 绿色 toast + 化身列表 stats 重新计算

#### 13.2.U.7 炼化 tab（蒸馏触发）

- 顶部：「蒸馏是单向动作。原眷族 Memory 不受影响，但新神职会取代 BaseClass 的派生源之一。」
- 2 个 section：
  - **晋升**（绿色 section）
    - 「晋升」按钮 → 弹模态
    - 模态字段：可选 kind 过滤（4 选 checkbox：experience / lesson / decision / problem，默认全选）
    - 提交按钮显示当前眷族的 Memory 计数 + 上次晋升时间（如有）
    - 提交 → POST → 成功后绿色 toast + 模态显示"新增 N 条 Memos"
  - **炼化**（紫红 section，需 `can_transmute_entity`）
    - "目标 slug" input + "目标神职 name" input + 4 kind 过滤
    - slug 实时查重（同 namespace 全局 unique）
    - 提交 → POST → 成功后跳转 `/base-classes/<新 slug>` 显示新 BaseClass
    - 错误处理：如 slug 冲突 → 红框 + 提示"该 slug 已被占用，建议用 [建议 slug 自动拼接 display_name 字段]"

#### 13.2.U.8 浮窗底部 Footer

固定 2 个按钮：

- 「查看所绑 Workspace 记忆」→ 跳 `/workspaces/:wid?focus=memory&entity=:eid`
- 「在拓扑中找到此 Node」→ 在 namespace 主页拓扑 tab 上 focus 此节点（v1 占位：toast "该 Workspace 主脑中尚无此节点 — 主脑节点功能 P15d+ 后续"）

### 13.1.U 记忆管理 UI 详写

#### 13.1.U.1 workspace dashboard 记忆 tab（主画布 tab 之一）

**顶部 stats bar**：
- 总眷族数（链路到 namespace tab 眷族）
- 累计 Memory 条目数（跨 4 kind）
- 待晋升候选数：Memory ≥ 20 的眷族数（蓝色徽章，hover 显示列表）

**眷族记忆卡片 grid**（3 列 desktop / 2 列 tablet / 1 列 mobile）：

每卡片内容：
- 大标题：眷族 display name + slug（mono 小字）+ rank badge
- 神职 chip
- 4 个 kind 小卡片（grid 2×2）：experience / lesson / decision / problem，每个显示数字
- 最近 lesson snippet（最多 80 字符截断）
- 操作 row：「查看完整记忆」/ 「晋升」/「炼化」（炼化需跳到 namespace 级）
- 健康度 badge：如果有失败化身的眷族 card 角标加红色描边

点击卡片行为：
- 单击 → workspace dashboard 主画布 blur + 暗化 + 打开 §13.1.2.U 单眷族记忆详情浮窗
- 双击 → 主画布新增持久化 tab：「记忆 · [眷族名]」（即 §13.1.2.U 详情页）

#### 13.1.U.2 单眷族记忆详情（持久化 tab 或浮窗）

**URL**：`/workspaces/:id?focus=memory&entity=:eid`

**Layout**（持久化 tab 占满主画布 / 浮窗 920×640）：

```
┌──────────────────────────────────────────────────────────────┐
│ HEADER: [← 返回 记忆 tab] 某某眷族 · 神职 chip · rank badge    │
├──────────────────────────────────────────────────────────────┤
│ Stats Bar (4 个)：4 个 kind 计数 + 上次晋升 / 上次炼化时间     │
├──────────────────────────────────────────────────────────────┤
│ 2 栏 grid:                                                    │
│ ┌──────────────────────────┐ ┌────────────────────────────┐  │
│ │ 左：Memory 汇总（主区域） │ │ 右：蒸馏操作区             │  │
│ │                          │ │                            │  │
│ │ [Tab: 全部][经验][教训]  │ │ ─ 晋升 (绿色 card) ─        │  │
│ │       [决策][问题]        │ │ 选 kind (4 checkbox)       │  │
│ │                          │ │ 当前 Memory N 条 / 上次 T  │  │
│ │ Memory 列表（按时间倒序）│ │ [立即晋升]                 │  │
│ │ 每条：kind badge + 时间 + │ │                            │  │
│ │       完整文本 + 来源     │ │ ─ 炼化 (紫红 card) ─        │  │
│ │       (Instance ID 前 8)  │ │ 目标 slug (实时查重)        │  │
│ │                          │ │ 目标 name                    │  │
│ │ virtualized list (window) │ │ kind 过滤 (4 checkbox)      │  │
│ │                          │ │ [立即炼化]                  │  │
│ │                          │ │                            │  │
│ │ [加载更多]               │ │ ─ 历史记录 ─                │  │
│ │                          │ │ 上次晋升：x 天前            │  │
│ │                          │ │ 上次炼化：x 天前            │  │
│ └──────────────────────────┘ └────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

**Memory 列表项**：

```
[经验] 2 小时前  from Instance #abc12345
测试发现 P9 拓扑节点拖拽时 z-index 偶尔丢失
[展开 ▼]  [复制]  [删除 super_admin only]
```

- 顶部行：kind badge + 相对时间 + 来源链接（Instance 名可点击跳该化身全屏）
- 主体：完整文本（默认折叠，长文 100 字截断 + [展开 ▼] 完整显示）
- 操作：[复制]（剪贴板）/ [删除]（仅 super_admin 可见，弹确认 modal）
- 长按 / 滑动（移动端）→ 出现快捷操作

**蒸馏表单**：

晋升 section：
- 4 个 kind checkbox（默认全选）
- 灰色文字显示当前 Memory 总数 + 上次晋升时间戳
- 「立即晋升」按钮（绿色）：点击 → 弹 spinner + toast "晋升中..."
- 完成后：toast "晋升成功 — 新增 N 条记忆在 Entity 上" + button 变成「已晋升 ✓」disabled 状态 + 显示时间戳

炼化 section：
- 输入：目标 slug input + 目标神职 name input
- slug 实时校验：去重 + 格式（kebab-case regex）/ 自动建议（从 display_name slugified）
- 4 个 kind checkbox
- 「立即炼化」按钮（紫红，点击 → spinner + toast "炼化中..."）
- 完成后：跳到新 BaseClass 详情页 + 历史记录 section 新增一行

#### 13.1.U.3 蒸馏完成 Result Modal

晋升完成时 **不弹 modal**，只用 toast + 状态切换。

炼化完成时弹全屏 modal（如 §13.4.2 定义）：

```
┌──────────────────────────────────────────────────┐
│ 炼化完成                                          ✕ │
├──────────────────────────────────────────────────┤
│ 新 BaseClass 已创建：[slug]                    │
│                                                  │
│ ┌─ Manifest Preview (key-value) ─┐               │
│ │ Name: 「某某眷族的技艺」          │            │
│ │ Slug: jin-xi-you-zi              │            │
│ │ Provider: anthropic / claude-3.5 │            │
│ │ Skills: [workflow-patterns, code-review...] ││
│ │ Tools: [shell, fetch_url, ...]  │            │
│ │ Commands: /execute /build /test  │            │
│ │ 基于 Memory: 23 entries          │            │
│ └──────────────────────────────────┘               │
│                                                  │
│ [查看神职详情] [立即基于此神职召唤新眷族] [关闭]  │
└──────────────────────────────────────────────────┘
```

[查看神职详情]：跳 `/base-classes/<slug>`
[立即基于此神职召唤新眷族]：跳 `/namespaces?tab=base-classes&focus=<slug>` + 自动展开「召唤」CTA

### 13.3.U 神职市场 UI 详写

#### 13.3.U.1 神职卡片 UI（namespace tab 神职 list item）

每卡片：

```
┌──────────────────────────────────────────┐
│ 神职名 [display name]              [悬停]│
│ slug: mi-shi · v1.0                    │
│                                          │
│ 1 句话职能描述（最多 100 字）            │
│                                          │
│ ┌─ 命令 ─┐ ┌─ Provider ─┐               │
│ │ /plan  │ │ claude-3.5 │              │
│ │ /deco  │ │ gpt-4o-mini│              │
│ └────────┘ └────────────┘               │
│                                          │
│ 已用: 5 眷族 · 12 化身 (跨 3 workspaces) │
│ ────────                                │
│ [查看详情]    [基于此召唤眷族 →]          │
└──────────────────────────────────────────┘
```

视觉层次：
- 头部（display name + version tag）：H3 16px semibold + small grey version
- 1 句话职能：14px regular slate-600
- 命令 chips：blue-50 背景 + blue-700 text，等宽字体，hover 出 description tooltip
- Provider chip：neutral + 实际模型名（hover 显示完整 prompt preview 首 50 字）
- 底部统计行：跨 workspace 全局聚合（count of entities / count of instances derived）
- 操作：
  - 「查看详情」按钮（中性）→ 神职详情浮窗
  - 「基于此召唤眷族 →」按钮（primary 蓝）→ §6 引导 Step 1 预选此神职

#### 13.3.U.2 神职详情浮窗（点击神职卡片触发）

**浮窗尺寸**：920×720（比眷族浮窗更大，因为内容多）

**Tabs**：
1. **概览**（默认）：display + 完整职能 + 命令集 + provider + 派生统计
2. **详细描述**：多段长 prose（来自 BaseClass manifest 的 description 字段，markdown 渲染）
3. **依赖基因**：列出该神职引用的深海基因
4. **派生眷族**：跨 workspace 列表（按 workspace 分组，每组列该 workspace 的眷族）

**概览 tab 内容**：

```
┌─────────────────────────────────────────────────────────────┐
│ Header:                                                    ✕ │
│ - 大 display name (H2)                                     │
│ - slug (mono small) + version tag                          │
│ - "召唤类" + "策划类" tags                                │
├─────────────────────────────────────────────────────────────┤
│ [Tabs: 概览 | 详细描述 | 依赖基因 | 派生眷族]              │
├─────────────────────────────────────────────────────────────┤
│ 概览 tab:                                                  │
│                                                             │
│ ┌─ Section: 职能描述（短） ──────────────────┐             │
│ │ 1 段短描述                              │              │
│ └────────────────────────────────────────┘              │
│                                                             │
│ ┌─ Section: 命令全集（不限 3 个） ──────────────┐          │
│ │ /plan 标记       "战略规划，列出可执行步骤"│             │
│ │ /decompose      "分解任务到子任务"        │             │
│ │ /prioritize     "按优先级重排"          │              │
│ │ /verify         "运行验证步骤"           │             │
│ │ (全部命令 + hover 显示 description)         │             │
│ └────────────────────────────────────────┘               │
│                                                             │
│ ┌─ Section: Provider 配置 ────────────────────┐             │
│ │ Provider: claude-3.5-sonnet                │             │
│ │ Fallback: gpt-4o-mini                     │             │
│ │ Max tokens: 4096                          │             │
│ │ 显示关键 override 字段                    │             │
│ └────────────────────────────────────────┘               │
│                                                             │
│ ┌─ Section: prompt 预览 ────────────────────┐             │
│ │ first 200 chars of system_prompt         │             │
│ │ "...[read more]"                          │             │
│ └────────────────────────────────────────┘               │
│                                                             │
│ ┌─ Section: 派生统计 ────────────────────────┐             │
│ │ 5 眷族 across 3 workspaces                │             │
│ │ 12 化身 running                            │             │
│ │ 累计该 BaseClass 召唤：x 次             │             │
│ └────────────────────────────────────────┘               │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ Footer:                                                     │
│  ← 关闭     [基于此神职召唤眷族 →]                       │
└─────────────────────────────────────────────────────────────┘
```

#### 13.3.U.3 详细描述 tab

- 渲染 markdown（来自 `BaseClass.description` 字段，markdown 源码）
- 顶部 sticky 锚点导航（自动生成 h2/h3 锚点列表）
- 渲染：标题 / 段落 / 列表 / 代码块 / 表格
- 代码块带语法高亮 + 复制按钮
- 长文支持 markdown `---` 分隔

#### 13.3.U.4 依赖基因 tab

- 上半：此 BaseClass 引用的深海基因列表（from manifest 的 `installed_genes` 字段）
- 每行：基因名（slug）+ kind chip + tags + 「查看基因」按钮（跳 §14b 详情）
- 下半：v1 暂不支持"从此页添加新基因"——baseClass 一旦创建基因锁定，要改去 §14b 改 BaseClass manifest

#### 13.3.U.5 派生眷族 tab

- 跨 workspace 列表（按 workspace 分组）

```
▼ Workspace: 我的开发组 (3)
  - 某某眷族 (mi-xi-you-zi)  深潜者   跳到实体详情 →
  - 另一个眷族 (ling-yi-ge)  浅识者   跳到实体详情 →
  - ...
▶ Workspace: 运维组 (2)
  - ...
```

- 每行右侧「跳到实体详情 →」按钮 → 跳 `/namespaces?tab=entities&focus=:eid`
- 总数 footer：「N 个 Workspace / M 个眷族 / K 个化身」

#### 13.3.U.6 双击神职卡片 → 神职详情全屏页

URL：`/base-classes/:slug`

- 同 §13.3.U.2 浮窗内容但全屏 + 左侧加 sidebar（"X 神职详情" + tab 切换）
- 顶部 breadcrumb：「神职 / my-slug」
- 操作栏：「基于此召唤眷族」primary 按钮 + 「编辑神职 manifest」（仅 super_admin，超链到 §14b）

#### 13.3.U.7 「基于此神职召唤眷族」CTA 全链路

1. 用户在神职卡片 / 详情页点击「基于此召唤眷族 →」
2. 跳到 `/namespaces?tab=base-classes&focus=:slug&action=summon`
3. namespace 主页主画布 blur + 暗化 + 全屏打开 §6 引导 modal
4. 引导 Step 1（神职选择）预选 `:slug`（高亮勾选状态）
5. 用户完成 Step 2 + Step 3 → 跳到 `/workspaces/:id?focus=memory&entity=:eid`（workspace dashboard 记忆 tab 定位此新眷族）

### 13.4.U 蒸馏 UI 跨场景一致性

蒸馏 2 动作在多个入口出现：

| 入口 | 看到的蒸馏 UI |
|---|---|
| workspace dashboard 记忆 tab 眷族卡 | 「晋升」 / 「炼化」按钮（炼化跳转 namespace）|
| 眷族详情浮窗 炼化 tab | 完整 2 动作表单（§13.2.U.7）|
| 眷族详情浮窗 当前化身 tab | 每行一个"回收"按钮（不是蒸馏，是资源回收，单独）|
| namespace tab 眷族 tab 详情 | 完整 2 动作表单 |

**所有入口的表单字段一致**：
- 晋升 = kind 过滤选 + 「立即晋升」按钮（4 checkbox 默认全选）
- 炼化 = slug + name + 4 kind filter + 「立即炼化」按钮

**API 端点统一**：`POST /api/v1/learning/entities/:eid/distill?action={promote|transmute}`

### 13.5.U 错误态 + 边界（展开）

#### 网络错误

- 蒸馏失败：toast "炼化失败：网络错误，请重试" + 「重试」按钮（恢复提交按钮可点）
- 详情加载失败：顶部 error banner + 「重试」按钮 + 「回到列表」链接

#### 权限错误

- 普通用户点击「基于此召唤眷族」→ 弹 toast "需要 can_summon_entity 能力位"
- 普通用户点击「软删除」→ 不显示该按钮（capacity-based hide）

#### 并发错误

- 详情浮窗 ETag mismatch（同时间其他人改了）
  - 红色 toast "该眷族已被其他人修改"
  - 「重新加载」按钮（拉最新并刷新表单）
  - 表单恢复为只读模式直到重新加载

#### 数据验证

- slug 格式不对：实时红框 + tooltip 提示
- slug 重复（虽然前端查重，后端也会复查）：红色 toast + 「恢复原 slug」按钮
- description 超长：实时计数器显示 500/500 红色

### 13.6.U a11y / i18n / 响应式

#### a11y

- 所有可点击 chip 都有 `aria-label`
- 浮窗打开时 trap 焦点（Esc 关闭）
- 表单字段用 `aria-describedby` 关联错误文案
- Tab 切换支持 `← →` 箭头键
- 「晋升」「炼化」按钮 hover 显示预计耗时（"约 5-10 秒"）

#### i18n

- 所有用户可见文案走 i18n key
- 关键字符串列表：
  - `entity.edit.displayName.label`、`entity.edit.slug.label`、`entity.edit.description.label`
  - `entity.tab.basic`、`entity.tab.capabilities`、`entity.tab.deepGenes`、`entity.tab.instances`、`entity.tab.distill`
  - `entity.button.save`、`entity.button.cancel`、`entity.button.delete`
  - `memory.tab.all` / `memory.tab.experience` / `memory.tab.lesson` / `memory.tab.decision` / `memory.tab.problem`
  - `distill.promote.submit`、`distill.transmute.submit`
  - `baseClass.tab.overview`、`baseClass.tab.description`、`baseClass.tab.genes`、`baseClass.tab.derived`
  - `nav.distill.promote`、`nav.distill.transmute`

#### 响应式

| 断点 | 眷族详情浮窗 | 神职详情浮窗 | 记忆详情 |
|---|---|---|---|
| mobile (<768px) | 全屏 sheet | 全屏 sheet | 上下堆叠（无 2 栏） |
| tablet (768-1023px) | 900×600 居中 | 900×680 居中 | 2 栏变窄 |
| desktop (≥1024px) | 920×640 默认 | 920×720 默认 | 完整 2 栏 |

---

*§13.1-§13.6 概念 + UI 详写完成。start-work 时 §13.U 章节可直接作为实现规格。*

- 蒸馏动作产生的是 **BaseClass**，**不是**深海基因
- BaseClass 定义 AI 的 prompt + commands + provider config
- 深海基因定义 AI 的 capabilities（skills / tools / mcps / lsps）
- 新 BaseClass 可以**引用**已存在的深海基因作为默认安装包（在 §13.3 详情页可以勾选）
- 蒸馏产物 ≠ 深海基因

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

> **2026-07-28 大重构**：从"多 tab 详情页"转向"VSCode 风 IDE 布局"。§7-§13 章节全部重写。

- §1 产品概述（本节）✓
- §2 三层正交概念：职阶 / 能力 / 知识（本节）✓
- §3 命名对照表（本节）✓
- §4 全局 UX 原则（本节）✓
- §6 首次运行引导 + 神职卡片组（本节）✓
- §7 AppShell + Sidebar 框架（VSCode 风）（本节）✓
- §8 Namespace 主页（`/namespaces`，多 tab）（本节）✓
- §9 Workspace Dashboard（`/workspaces/:id`，VSCode-IDE 布局）（本节）✓
- §10 Composer Side Panel（右侧常驻 + 可全屏）（本节）✓
- §11 Topology Dashboard（主画布默认 tab，节点浮窗 + 双击持久化）（本节）✓
- §12 调试页（namespace tab 内）（本节）✓
- §13 记忆 + 眷族管理 + 神职市场（改名）（本节）✓
- §13.6 能力生命周期模型：Memory → Capability → Gene → BaseClass（4 级跳，用户原话澄清后定义）
- §13.UX UI 详写（start-work 直接落地用，含眷族详情 / 记忆管理 / 神职市场 UI 规格）
- §14 觉醒基因 UI（本节）✓
- §14b 深海基因 UI（本节）✓
- §14c 知识 UI（本节）✓
- §15 i18n 覆盖矩阵 + 错误显示规范（本节）✓
- §16 架构变更说明（15d+ 大重构）（本节）✓

---

## §16 架构变更说明（2026-07-28 大重构）

> 本节解释 15e PRD 从"多 tab 详情页"到"VSCode 风 IDE 布局"的架构变更。读者不必把 §7-§13 当成先后两个版本理解——这是 15e 交付的真实目标状态。

### 16.1 重构触发

在用户原话反馈中提到："**workspace 主页应该是 dashboard（拓扑）作为主页面，然后点击节点弹窗口；VSCode 那种 IDE 布局就挺好**"。这个反馈推动 PRD 大重构。

### 16.2 重构前 vs 重构后

| 维度 | 重构前（早期版本） | 重构后（当前 PRD 状态） |
|---|---|---|
| **Workspace 主页** | `/workspaces/:id` 是 3-tab 详情页（契印 / 眷族 / 主脑）| `/workspaces/:id` 是 VSCode 风 dashboard（默认 tab = 拓扑，可切换 4 个 tab） |
| **主画布** | 单页滚动，3 个 tab 切换 | 多 tab + 可切换 + 可持久化（dblclick 节点开新 tab） |
| **Composer** | 全屏独立路由 `/workspaces/:id/composer` | 右侧常驻 side panel，可拖缩 / 全屏 / 关闭 |
| **节点交互** | 拓扑是单独路由，只有点击跳详情 | 拓扑默认在 dashboard，hover tooltip / click 浮窗 / dblclick 持久化 |
| **眷族管理位置** | workspace tab 「眷族」内 | namespace tab 「眷族」内 |
| **神职管理位置** | 全局 `/base-classes` | namespace tab 「神职」内，整合入 `/namespaces` |
| **登录默认落点** | `/workspaces` | **`/namespaces`**（明确区分 namespace / workspace 两层） |
| **Sidebar 入口** | 9 个展开入口 | 6 个折叠态图标 + 展开态二级列表（VSCode 风） |

### 16.3 不动的部分

- **§1-§6** 产品概述 + 三层正交概念 + 命名对照 + UX 原则 + 首次运行引导 — **完全不动**
- **§14 / §14b / §14c** 觉醒基因 / 深海基因 / 知识 UI — 完全不动（这些是后台管理 / 配置 UI，不在 IDE 画布内）
- **§15** i18n 覆盖矩阵 — 几乎不动（少量 i18n key 需要更新名字以匹配新结构）

### 16.4 重构带来的新结构

**新路由结构**（RESTful）：

```
/login
/namespaces                          ← 登录默认落点，namespace dashboard
/namespaces?tab=workspace           (默认 tab)
/namespaces?tab=base-classes
/namespaces?tab=contracts
/namespaces?tab=entities
/namespaces?tab=debug
/workspaces/:id                     ← workspace dashboard (VSCode-IDE)
/workspaces/:id?fullscreen=:iid     全屏打开指定化身
/workspaces/:id?focus=memory&entity=:eid  记忆 tab + focus 眷族
/contracts?focus=:uid
/entities?focus=:eid
/base-classes
/base-classes/:slug
```

**IDE 布局区域**（workspace dashboard 内）：
- 主画布多 tab：拓扑 / 契印 / 化身 / 记忆
- Composer Side Panel（右侧，常驻）
- Sidebar 活动栏（左侧，可折叠）
- Status Bar（底部）

### 16.5 Navigator 跳转模型

按用户原话："**关联对象都得是 navigator，点完了能直接点到那个对象的设置/信息页**"。所有跨对象跳转：

| 起点 | 点击 | 终点 |
|---|---|---|
| workspace dashboard 节点 | 浮窗"神职 chip" | `/namespaces?tab=base-classes&focus=<slug>` |
| workspace dashboard 节点 | 浮窗"跳到所在 workspace" | 当前 workspace dashboard + 全屏打开 |
| namespace tab 眷族卡 | 神职 chip | 神职市场该 BaseClass 详情 |
| namespace tab 眷族详情 | "跳到 workspace" | workspace dashboard + focus 到该眷族记忆 |
| 主脑 / 各脑区 | 任意关联对象 | 对应对象的详情页 |

### 16.6 节点交互的 3 档

| 交互 | 触发 | 内容 |
|---|---|---|
| **hover tooltip** | 鼠标悬停节点 | 心智状态 / loop_status / 续命次数 / 链接 |
| **click 浮窗** | 单击节点 | 主画布 blur + 暗化 30% + 浮窗显示详细信息 + 操作按钮 |
| **dblclick 持久化** | 双击节点 | 在主画布 tab 栏新增 tab，可切换其他 tab 后切回仍在此 |

### 16.7 反向影响

重构导致 §7-§13 章节整体重写，但 **§1-§6 / §14-§15 内容** 完全不变。这意味着 15e-rename wave（代码层面）的工作不变，UI 重写的工作量更大。

### 16.8 待办（重构后还需要补的事）

| 项 | 负责范围 |
|---|---|
| §6 引导 → 完成后导航 `/workspaces/:id` 改为 `/namespaces`（如果 workspace 不存在） | 修正 §6.5 "完成后导航" |
| §12 调试页 tab 化后 URL 跳转 | 跟 §12 链接 |
| §15 i18n 矩阵更新 key 命名（如 `nav.topology` → `nav.topologyDashboard` 之类） | 等 §7 定版后做 |

这些是 follow-up，不影响当前 PRD 整体一致性。

---

*§1-§16 完成 (Todo #1-#11 + 重构记录)。15e PRD v2 完成，等待用户整体审阅。*