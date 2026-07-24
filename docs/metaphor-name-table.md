# Cocoa Metaphor Name Table

## Preamble

Cocoa uses a **Hybrid metaphor system**: the product skin (what users see) is cultural, drawing on biological and mystical/alchemical imagery, while the internals (code, database schemas, API identifiers) stay technical English. This table is the single source of truth for every concept name in the Cocoa domain. Downstream documents (terminology, domain model, preset manifests, UI) derive their identifiers from the rows below.

The table is organized into four sections: **structure terms** (biological metaphor for the office-employee topology), **presets** (mystical/alchemical names for agent roles), **lab ranks** (seniority axis orthogonal to presets), and **code-term-only sub-entities** (technical identifiers with no display name in P1). Each row maps a code-level identifier to its biological metaphor name, its product-skin display name, and a short description of its role in the system.

Some concepts are marked **deferred**: Ring=环 exists as a placeholder because the ring topology is a P3/P4 concern, but the name is locked here so downstream work can reference it. Code-term-only rows have empty bio-name and display-name cells; they are internal identifiers the P2 data layer uses but do not yet surface in the product UI.

## Name Table

### Structure Terms

| code-term | bio-name | display-name | role |
|-----------|----------|-------------|------|
| Office | 菌落 | 菌落 | 工作空间的组织单元，容纳多个员工实例的边界容器 |
| Employee | 细胞 | 细胞 | 持久的角色身份，由灵格预设和共享记忆定义，一个员工可有多个分身 |
| Instance | 分身 | 分身 | 员工在某个菌落中的具体化身，拥有独立工作区和运行时状态 |
| Preset | 灵格 | 灵格 | 员工的预设模板，定义技能、工具、模型和指令 |
| Gene | 基因 | 基因 | 可学习的技能模块，可注入员工灵格，由 /distill 从记忆中提炼 |
| Memory | 基因组 | 基因组 | 员工共享的累积经验，跨实例持久化，追加写入，不自动加载到会话上下文 |
| Blackboard | 共生面 | 黑板 | 菌落内共享的实时协作面板，权限控制，支持文件读写 |
| Vault | 冰封库 | 冰封库 | 冷存储归档库，长期保存，由 /archive 命令写入 |
| Corridor | 突触 | 突触 | 员工间的邻接关系边，定义可通信的邻居集合，近邻消息路由 |
| Ring | 环 | 环 | 显式协作环，限定上下文的作用域（P3/P4 实现，当前占位） |

### Presets

| code-term | bio-name | display-name | role |
|-----------|----------|-------------|------|
| Planner | | 密士 | 规划与分解任务的预设角色 |
| Worker | | 铸金 | 执行与构建的预设角色 |
| Oracle | | 灵视 | 审查与验证的预设角色 |
| Explorer | | 游魂 | 探索与调研的预设角色 |
| Reviewer | | 衡判 | 评审与判定的预设角色 |
| Human | | 总监 | 人类操作者，总监级别，拥有审批权 |

### Lab Ranks

| code-term | bio-name | display-name | role |
|-----------|----------|-------------|------|
| Intern | | 实习生 | 无状态热加载，不记往事，每次调用全新启动 |
| Researcher | | 研究员 | 完整预设加记忆，持久化，可积累经验 |
| Director | | 总监 | 人类操作者，最高权限，审批和转发 |

### Code-term-only Sub-entities

| code-term | bio-name | display-name | role |
|-----------|----------|-------------|------|
| User | | | 人类用户的认证身份（P2 数据层实体） |
| EmployeePreset | | | 预设的持久化记录，存储 manifest 和版本信息（P2 数据层实体） |
| Membership | | | 员工或用户在菌落中的成员关系，含坐标和权限（P2 数据层实体） |
| BlackboardFile | | | 黑板上的文件记录，含存储键和元数据（P2 数据层实体） |
| VaultEntry | | | 冰封库中的归档条目，记录来源和归档时间（P2 数据层实体） |
| MemoryEntry | | | 记忆的追加日志条目，按员工和时间索引（P2 数据层实体） |

> **Footnote:** The six code-term-only rows above are internal identifiers for the P2 core domain model. They have no bio-name or display-name in P1 because they are data-layer entities that do not surface as independently named concepts in the product UI. They may acquire display names in later phases when the portal visualizes them.

## Collision Verification

No preset display-name (密士, 铸金, 灵视, 游魂, 衡判, 总监) equals any structure display-name (菌落, 细胞, 分身, 灵格, 基因, 基因组, 黑板, 冰封库, 突触, 环). The display-name 总监 appears in both the Human preset and the Director rank; this is intentional because the Human preset is the Director rank, a single concept viewed from two angles (preset selection and seniority axis). All other display-name values are unique across the named roles in this table. Verified by inspection of the table above.