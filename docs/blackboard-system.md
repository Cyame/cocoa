> **Pre-v4 reference**: Conflict with `.omo/evidence/audit-product-design.md` → audit wins. Awaiting v4 PRD rewrite.
>

# 中央主脑（CentralHub）系统

> **15d 重构 + 4 脑区设计（2026-07-28）**：本文档描述 15d+ 的目标架构。代码层面 Blackboard 表名仍存在，15d-rename wave 会同步改为 CentralHub + 4 脑区子表（穹窿 / 额叶 / 脑干 / 小脑）。
>
> **Display 名 = 主脑 / Central hub**，backend real name = `CentralHub`（含 4 脑区子表，分子表方案）。

中央主脑是 Workspace 内的协作中枢容器。1 个 Workspace 有且只有 1 个 CentralHub（1:1），里面包含 4 个独立功能的子区（脑区），每个脑区对应 1 个独立子表。

## 1. CentralHub 主表 + 4 脑区子表

```
central_hubs (1:1 per workspace)
├── fornix_files (1:N)            # 穹窿 — 工作目录
├── frontal_lobe_kanbans (1:N)    # 额叶 — Kanban + Todo
├── brainstem_schedules (1:N)     # 脑干 — 定时任务
└── cerebellum_agents (1:1)       # 小脑 — 中央 agent
```

### 1.1 脑区对照表

| 脑区 | Backend 表 | Display (zh) | 功能 |
|---|---|---|---|
| 穹窿（fornix） | `fornix_files` | 穹窿 | Workspace 共通工作目录（files / shared assets / attachments）— 继承现有 BlackboardFile |
| 额叶（frontal lobe） | `frontal_lobe_kanbans` | 额叶 | Kanban + Todo（继承 oh-my-openagent 的 todo 系统） |
| 脑干（brainstem） | `brainstem_schedules` | 脑干 | 定时任务 / 延时任务（cron-like 调度，Workspace 作用域） |
| 小脑（cerebellum） | `cerebellum_agents` | 小脑 | 1 个系统级中央 agent，仅服务主脑，不参与 Workspace 整体编排 |

### 1.2 数据模型：分两阶段落地

| 阶段 | 状态 |
|---|---|
| P15d（当前 PRD） | 概念设计 + 文档落地 |
| P15d-rename wave | schema 落地为分子表：central_hubs + 4 张子表 |

**P15d 之前**：现有 Blackboard 单表（含 content / manual_notes + BlackboardFile 子表结构）继续运行。15d-rename wave 时拆为分子表。

### 1.3 数据模型示意（target architecture）

```python
# Container — 1:1 per Workspace
class CentralHub(BaseModel, Base):
    workspace_id: str      # FK → workspaces.id (1:1)
    # 4 脑区子表的 container，不直接存储内容
    created_at, updated_at, deleted_at

# 穹窿 — 文件
class FornixFile(BaseModel, Base):
    central_hub_id: str        # FK → central_hubs.id
    parent_path: str | None
    name: str
    is_directory: bool
    storage_key: str           # UUID, opaque ref
    content_type: str | None
    file_size: int | None
    uploader_user_id: str | None
    uploader_instance_id: str | None   # XOR
    created_at, deleted_at

# 额叶 — Kanban + Todo
class FrontalLobeKanban(BaseModel, Base):
    central_hub_id: str
    title: str
    status: enum(backlog, in_progress, done, blocked)
    assignee_user_id: str | None
    assignee_instance_id: str | None   # XOR
    created_at, updated_at, deleted_at

# 脑干 — 调度
class BrainstemSchedule(BaseModel, Base):
    central_hub_id: str
    name: str
    schedule_type: enum(cron, interval, delay)
    cron_expression: str | None
    interval_seconds: int | None
    next_run_at: datetime
    last_result: enum(success, failed, skipped) | None
    enabled: bool
    created_at, deleted_at

# 小脑 — 系统级 agent (1:1 per central hub)
class CerebellumAgent(BaseModel, Base):
    central_hub_id: str        # 1:1
    base_slug: str             # 关联到内置 BaseClass "cerebellum-baseclass"
    loop_status: enum(...)
    heartbeat_at: datetime
    installed_genes: JSONB    # 默认安装的深海基因集
    system_prompt: text
    created_at, updated_at
    # 注意：小脑 agent **不**可软删
```

## 2. 权限模型

Workspace-scoped, role-gated access control. 4 脑区共享同一权限层级：

```
owner (2) > editor (1) > viewer (0)
```

### 2.1 能力位（per 脑区）

| 操作 | 能力位 |
|---|---|
| 读取任意脑区 | `can_view_central_hub` |
| 编辑穹窿（写文件） | `can_edit_fornix` |
| 创建/编辑额叶 todo | `can_edit_frontal_lobe` |
| 配置脑干调度 | `can_manage_brainstem` |
| 查看/重启小脑 agent | `can_view_cerebellum` |
| 修改小脑 prompt | `can_manage_cerebellum_agent`（限超管） |
| 中央枢纽管理 | `can_manage_central_hub`（限超管） |

### 2.2 现有 P6 能力位映射

P15d 之前，能力位用 `can_edit_blackboard` 等 P6 命名。15d-rename wave 时：

| 旧 | 新 |
|---|---|
| `can_edit_blackboard` | `can_edit_fornix` |
| `can_view_blackboard` | `can_view_central_hub` |
| `can_archive_file` | `can_archive_fornix_file` |

## 3. API 路径（目标态）

```
# 主脑（4 脑区容器）
GET    /api/v1/central-hubs/{wid}                            # 概览
GET    /api/v1/central-hubs/{wid}/overview                    # 4 脑区状态聚合

# 穹窿（工作目录）
GET    /api/v1/central-hubs/{wid}/fornix/files
GET    /api/v1/central-hubs/{wid}/fornix/files/{file_id}
POST   /api/v1/central-hubs/{wid}/fornix/files
PATCH  /api/v1/central-hubs/{wid}/fornix/files/{file_id}
DELETE /api/v1/central-hubs/{wid}/fornix/files/{file_id}
POST   /api/v1/central-hubs/{wid}/fornix/files/{file_id}/archive

# 额叶（Kanban）
GET    /api/v1/central-hubs/{wid}/frontal-lobe/kanbans
POST   /api/v1/central-hubs/{wid}/frontal-lobe/kanbans
PATCH  /api/v1/central-hubs/{wid}/frontal-lobe/kanbans/{id}

# 脑干（调度）
GET    /api/v1/central-hubs/{wid}/brainstem/schedules
POST   /api/v1/central-hubs/{wid}/brainstem/schedules
PATCH  /api/v1/central-hubs/{wid}/brainstem/schedules/{id}
DELETE /api/v1/central-hubs/{wid}/brainstem/schedules/{id}

# 小脑（中央 agent）
GET    /api/v1/central-hubs/{wid}/cerebellum                  # agent 详情
GET    /api/v1/central-hubs/{wid}/cerebellum/memory           # 内部 memory
POST   /api/v1/central-hubs/{wid}/cerebellum/restart          # 超管
PATCH  /api/v1/central-hubs/{wid}/cerebellum/prompt           # 超管
```

**迁移过渡**：当前代码 `/api/v1/blackboard/...` 仍可用。15d-rename wave 同步切到 `/central-hubs/...`，前端调用约定同时迁移。

## 4. 小脑 agent（Cerebellum Agent）— 特殊系统级 agent

### 4.1 与普通 Entity（眷族）的区别

| 维度 | 眷族（Entity） | 小脑 agent |
|---|---|---|
| 创建者 | 真人操作员通过 §6 引导创建 | 系统初始化时自动创建（per workspace） |
| 是否可软删 | 是 | **否**（系统级，强制存在） |
| BaseClass 关联 | 11 神职之一 | 内置神职 `cerebellum-baseclass`（系统专属） |
| 出现位置 | 心灵图景节点 / 神职 tab | **仅**主脑视图（小脑 tab），不出现在拓扑 |
| 派活方式 | Composer 派给它 | 系统自动派（脑干调度 / 状态监控 / 感知聚合） |
| 是否可见 | 可见，可操作 | 可见，但只有超管能修改 prompt |

### 4.2 核心职责

- **感知聚合**：把穹窿 + 额叶 + 脑干的状态聚合为 Workspace 级视图
- **状态监控**：巡检 4 脑区健康度，根据规则触发预警
- **定时任务执行人**：脑干调度触发的中央智能任务（小脑是默认执行者，但不是唯一）
- **跨脑区一致性**：检查 todo 是否与共享上下文一致、调度是否有冲突等

### 4.3 资源消耗控制

- 小脑 agent 默认 idle 状态，按需唤醒
- 唤醒触发：脑干调度到达 / 穹窿文件变更 / 额叶 todo 创建
- 唤醒超时（默认 30s）自动回 idle
- 永不公开作为普通 Instance 可交互（Topology viz 看不到）

## 5. 现有 P6 黑板概念 → 15d 映射

| P6 概念 | 15d 映射 | 备注 |
|---|---|---|
| Blackboard（单表） | CentralHub（容器表） + 4 脑区子表 | 15d-rename wave 拆表 |
| BlackboardFile | FornixFile（穹窿的子表） | 直接重命名 + 表名调整 |
| Blackboard.content / manual_notes | 降级为穹窿的 `centralized_notes` 字段（中央备注），或迁出 | 待定 |
| Vault（冷存储） | 保留，但路径调整到 `central-hubs/{wid}/fornix/vault` | 仍为穹窿的子功能 |
| MemoryEntry | Memory（分子表 / 跨 workspace） | 现有 P6 行为保持，直到 P13 之后扩展 |

---

*Last updated: 2026-07-28 (15d 重构 + 4 脑区分子表方案).*
