# AGENTS.md - Cocoa 开发指南

> 给人类贡献者与 AI Agent 共同遵守的开发规范。读者包括 Claude / OpenCode / Cursor / Codex 类工具，以及项目内的开发者。

## 项目概述

Cocoa 是多 Agent 控制台（multi-agent control studio）。本仓库已完成 **P7 实例运行时与 K8s 部署脚手架**，包含：

| 组件 | 技术栈 | 状态 |
|------|--------|------|
| `cocoa-backend/` | Python 3.12 + FastAPI + SQLAlchemy (async) + asyncpg + Alembic | P2 引入 12 核心域模型；P3.5 加入 Event 模型；P9 加入 CorridorNode 模型 + glow helper + events 查询端点 + live-status 聚合端点 + Membership 坐标迁移（`hex_q/hex_r` → `posx/posy`）；P10 加入 Learning 子系统（DistillationEngine Protocol + AggregatingDistiller 启发式引擎 + 3 个 learning API 端点 + LEARNING_COMMANDS 第 4 命令族 + portal Learning 页面 + 零 schema 变更），合计 14 models + 351+ 测试 |
| `cocoa-portal/`  | React 19 + Vite 8 + TypeScript + Tailwind CSS v4 + Bun + lucide-react + Zustand | P9 first UI（14 todos：7 页面 + topology viz + CorridorNode + interaction modes + 零新增 npm 依赖） |
| `cocoa-artifacts/` | Dockerfile + K8s 清单（Deployment/Service/ConfigMap/PVC/NetworkPolicy） | P7 已完成 |
| `.github/workflows/` | CI 基础（lint + build） | 骨架 |

后端构建上下文：**`cocoa-backend/`，不是仓库根目录**。`pyproject.toml`、`alembic.ini`、`.env` 都在 `cocoa-backend/` 下。`uv sync` / `alembic` 命令必须从该目录执行，或通过 `dev.sh` 自动 `cd`。

## 构建/测试命令

### 后端（cocoa-backend）

```bash
cd cocoa-backend
uv sync                                      # 安装依赖
uv run uvicorn app.main:app --reload --port 4510
uv run pytest                                # 运行全部测试
uv run pytest tests/test_xxx.py              # 运行指定文件
uv run pytest tests/test_xxx.py::test_func   # 运行指定函数
uv run ruff check .                          # Lint
uv run ruff check --fix .                    # Lint + 自动修复
```

### 开发数据库（后端）

后端使用本地 PostgreSQL（>= 16）上的**两个独立数据库**，职责严格分离：

| 数据库 | 用途 | 管理者 |
|--------|------|--------|
| `cocoa_dev` | 开发 schema + 你的手工数据 | **Alembic 独占**（`alembic upgrade head`） |
| `cocoa_test_template` | pytest 模板（会话级） | conftest 建/删 |
| `cocoa_test_<hex>` | pytest 每测试克隆库 | conftest 建/删 |

**铁律：pytest 绝不触碰 `cocoa_dev`。** 每个需要 DB 的测试从 `cocoa_test_template`（Alembic 迁移构建）克隆一份私有库，跑完即删 —— 你在 `cocoa_dev` 里的数据永远安全。测试代码中禁止出现 `cocoa_dev` 连接串。

```bash
# 首次建库（只需要 cocoa_dev；测试库由 conftest 自动管理）
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE cocoa_dev;"

# 应用 schema（cocoa_dev 只走 Alembic，禁止 create_all）
cd cocoa-backend && uv run alembic upgrade head
```

无本地 Postgres 时可用 `cocoa-backend/docker-compose.dev.yml` 起一次性容器（端口 5433，避免与本地 5432 冲突）。

### 前端（cocoa-portal）

```bash
cd cocoa-portal
bun install
bun run dev          # http://localhost:5173
bun run build        # 生产构建
tsc -b               # 类型检查
bun run lint         # Lint (Biome)
bun run test         # 测试 (Vitest)
```

### 一键启动

```bash
./dev.sh            # 后端 (4510) + 前端 (5173)，彩色日志，Ctrl+C 清理
./dev.sh --fresh    # 强制重建 .venv 和 node_modules
```

## 编码风格

### 命名约定

| 类型 | 规则 |
|------|------|
| React 组件文件 | PascalCase（如 `UserProfile.tsx`） |
| React Hooks | camelCase（如 `useAuth.ts`） |
| 工具函数 / composable | camelCase（如 `useAuth.ts`） |
| 类型 / 接口 | PascalCase（如 `UserInfo`） |
| 常量 | UPPER_SNAKE_CASE |
| Python 模块 / 函数 | snake_case |
| Python 类 | PascalCase |
| 布尔变量 | `is_` / `has_` / `can_` 前缀 |
| 通用 | 禁止中文命名；禁用过激缩写（API / URL / ID / DB 保留） |

### Emoji 禁用规则（强制）

**未经用户明确允许，禁止在任何地方使用 emoji**，包括但不限于：

- React 模板中的图标位 —— 改用 `lucide-react` 组件
- 提示文案、占位符、label —— 纯文本
- 日志输出、Toast 消息 —— 纯文本
- 文档、commit message、PR 描述 —— 纯文本
- HTML 实体字符 / 几何符号当图标 —— 同样禁止，一律改用 Lucide 组件

```tsx
{/* 禁止 */}
<span>搜索实例...</span>
<span>提示</span>

{/* 正确 */}
<Search className="w-4 h-4" />
<Bell className="w-4 h-4" />
```

图标统一从 `lucide-react` 按需导入，常用尺寸 `w-4 h-4`（导航 / 按钮）、`w-5 h-5`（Logo / 标题）。

### 软删除规则（强制）

**所有数据删除必须使用逻辑删除（soft delete），严禁物理删除。**

- 删除操作统一设置 `deleted_at = func.now()`，封装在 `BaseModel.soft_delete()` 中
- 所有数据库查询必须过滤已删除记录：`Model.deleted_at.is_(None)`
- 级联删除（删父记录时连带子记录）需手动设置子记录的 `deleted_at`
- 禁止 `db.delete()`、禁止 `DELETE FROM` 原生 SQL

**唯一约束必须用 Partial Unique Index**：

```python
# 正确
Index("uq_xxx", "col_a", "col_b",
      unique=True, postgresql_where=text("deleted_at IS NULL"))

# 错误 —— 软删除后同键位无法重建
UniqueConstraint("col_a", "col_b", name="uq_xxx")
```

`UniqueConstraint` 覆盖全表（含软删除记录），软删除后再次 INSERT 相同键会触发 `IntegrityError` → 500。Partial Unique Index 只对 `deleted_at IS NULL` 的活跃记录生效。

### Alembic 迁移规则（强制）

**新增或修改数据模型后，必须用 `alembic revision --autogenerate` 生成迁移文件，并作为同一个 commit 的一部分提交。**

- **禁止手写 revision ID** —— 必须由命令自动生成。手写假 ID 会让迁移链冲突、阻塞升级
- **禁止只加 Model 不加迁移** —— 启动走 `alembic upgrade head`，缺迁移 = 表不存在 = 启动崩溃
- **Review 生成的迁移**：autogenerate 无法检测列重命名（会生成 DROP + ADD），Partial Unique Index 需手动调整
- **迁移文件必须提交到 Git**：`alembic/versions/` 下的文件是代码的一部分

```bash
# 标准流程
cd cocoa-backend
uv run alembic revision --autogenerate -m "add users table"
uv run alembic upgrade head    # 本地验证
# 然后将生成的 .py 文件与 Model 改动一起 commit
```

### 导入完整性

在函数 / 异步上下文（如 FastAPI `lifespan`）内使用模型或工具类时，必须确保该作用域内有对应的 `import`。每个 `async with` 块都是独立作用域，需要各自补齐依赖。不要假设外层已导入。

### i18n 文案

新增或修改用户可见文案时，必须接入 i18n 词条，不允许在模板 / 脚本中硬编码中文 UI 文案（专有名词除外）。

- 词条命名：小写点分级，如 `errors.auth.token_invalid`
- 调用必须使用命名参数：`t('errors.instance.not_found', { name })`
- 后端错误响应必须包含 `error_code` + `message_key` + `message`

### API 约定

Cocoa 后端 API 遵循 `docs/api-architecture.md` 中的完整约定，核心规则摘要：

1. 业务 API 全部 `/api/v1/`，仅破坏性变更升 v2；运维端点（`/health`、`/docs`、`/openapi.json`）留在根路径不版本化
2. JSON 字段 snake_case 端到端（Pydantic 字段即线上字段，无别名转换层）
3. 资源命名：复数 kebab-case（`/employee-presets`），嵌套 ≤2 层
4. 动作端点：`POST /resources/{id}/action`（Stripe 风格，不混用 `:action` 语法）
5. 错误响应格式：`{error_code, message_key, message, details, request_id}`——后端同时注册 `CocoaError`、`StarletteHTTPException`、`RequestValidationError`、`Exception` 四处理器
6. 弃用：`Deprecation` 头（RFC 9745，`@unix时间戳`）+ `Sunset` 头（RFC 8594）+ `Link: rel="deprecation"`
7. `DELETE` 映射软删除返 204；创建成功返 201；时间戳 ISO 8601 UTC；路径参数 UUID
8. 分页：游标分页默认（`?limit=&cursor=`），偏移分页备选（`?limit=&offset=`），排序 `?sort=-created_at`
- 日志/事件/队列约定见 `docs/observability.md`
- Preset 系统设计见 `docs/preset-system.md`（P4 Agent Presets 核心文档）
- 消息系统设计见 `docs/messaging-system.md`：消息拓扑、近邻投递、激活触发器、Directive 路由
- 黑板系统设计见 `docs/blackboard-system.md`：Blackboard 被动状态模块、BlackboardFile 虚拟文件系统、Vault 归档、MemoryEntry 追加日志、权限模型
- 实例运行时系统见 `docs/runtime-system.md`：Instance 生命周期模型、CRUD API、K8s 部署脚手架、多实例隔离、Langfuse 集成预留
- Harness 系统设计见 `docs/harness-system.md`：D11 控制面、Supervisor + 4 个确定性熔断器、Boulder 循环引擎、5 个控制命令、Notepad 契约、Agent Runtime 骨架、Control Downlink 双路径机制
- Portal 系统设计见 `docs/portal-system.md`：React 19 架构、7 页面路由表、事件查询 API、live-status 聚合端点、CorridorNode CRUD、Composer 分段语义、Topology viz 算法（glow 映射 + 连接动画）
- Learning 子系统设计见 `docs/learning-system.md`（P10）：DistillationEngine Protocol 可插拔接口、AggregatingDistiller 启发式算法（按 MemoryKind 分组聚合 + 关键词提取 + 模板生成）、LEARNING_COMMANDS 第 4 命令族（`/distill` `/consolidate` `/reflect`）+ P5 路由优先级表、3 个 Learning API 端点（summary + distill + preset fetch）、portal EmployeeLearningPage + EmployeePreset 零迁移新增 + 351+ 测试

**P9 Portal**: React 19 + Vite 8 + TypeScript + Tailwind CSS v4 + Zustand + react-router v7, 零新增 npm 依赖。7 个页面（Login / Office list / Office detail / Instance detail / Composer / Debug / Topology viz）。Topology viz 是旗舰功能：SVG 圆形节点 + 外框发光（`loop_status` → glow color）+ pan/zoom canvas + 3 种交互模式（Select/Connect/Move）+ 连接线消息传递流光动画。CorridorNode 是 first-class canvas 元素（`posx/posy` + `display_name` + `status`），支持 M<->M / M<->CN / CN<->CN 三种走廊连接。全量前端 type-check + lint + build + vitest 通过；后端 315+ 测试零回归。

**P9 坐标迁移**：`Membership.hex_q → posx`、`Membership.hex_r → posy`（Alembic `op.alter_column` rename，保留数据）。新增 partial unique index `uq_memberships_office_pos` 约束 `(office_id, posx, posy)` 在活跃记录中唯一。`grep -rn "hex_q\|hex_r" cocoa-backend/app cocoa-backend/tests` 应 0 命中（除历史 alembic 迁移文件）。

**P9 CorridorNode 模型**：`corridor_nodes` 表 — `office_id, posx, posy, display_name, glow_color, status`。5 个 CRUD 端点（`GET list / GET id / POST / PATCH / DELETE`）挂在 `/learning/corridor-nodes`。`Corridor` 表多态扩展：`from/to_membership_id` 改为 nullable + 新增 `from/to_corridor_node_id` nullable；CHECK 约束确保每条边两端恰好各一个非空。三种连接：成员 ↔ 成员 / 成员 ↔ 走廊节点 / 走廊节点 ↔ 走廊节点。

**P9 Glow 映射**：`app/core/glow.py::loop_status_to_glow(status)` 返回 `GlowColor(color, intensity)`，覆盖 6 种 LoopStatus（running=#10b981/strong, idle=#eab308/medium, paused=#94a3b8/weak, interrupted=#ef4444/medium, completed=#3b82f6/low, failed=#dc2626/strong）+ 未知兜底。`user_membership_glow()` 固定 #4f46e5/medium。`GET /api/v1/offices/{id}/live-status` 聚合所有 membership 的 glow state，topology viz 每 2 秒轮询。

**P8 Harness**: D11 control plane lives in `app/core/harness_supervisor.py`. In-memory loop-state registry + 4 deterministic circuit breakers. Handler updates ONLY the registry (no DB writes — P3.5 contract). DB mutations happen via `handle_*` direct mutators from the API endpoint layer. Control commands (`/interrupt /pause /resume /status /snapshot`) are the third command category after P4 global scope-ops and per-preset commands.

**P10 Learning**: Skill-distillation layer bridging employee memory to reusable agent presets. `DistillationEngine` Protocol in `app/core/distillation.py` defines the pluggable interface; `AggregatingDistiller` is the default heuristic implementation (no LLM). 3 API endpoints in `app/api/v1/learning.py`: `GET /learning/memories/{id}/summary`, `POST /learning/employees/{id}/distill`, `GET /learning/presets/{id}`. `LEARNING_COMMANDS` (`/distill`, `/consolidate`, `/reflect`) form the fourth command family registered in `app/core/preset_registry.py`, routed by `app/core/directive_router.py::_route_learning_directive()` with priority between control and global commands. Portal `EmployeeLearningPage` at `/employees/:id/learning` shows memory summary + distill form + result modal. See `docs/learning-system.md`.

**Command family registry** (four families, priority-ordered in `directive_router.py::route_turn()`):

| Family | Commands | Reg | Route Target | Requires @target |
|--------|----------|-----|--------------|-----------------|
| GLOBAL | `/read`, `/list`, `/write`, `/archive` | P4 | Message corridor | No |
| PER-PRESET | Defined in `manifest.commands` | P4 | Message corridor | Yes |
| CONTROL | `/interrupt`, `/pause`, `/resume`, `/status`, `/snapshot` | P8 | Harness Supervisor | Yes |
| LEARNING | `/distill`, `/consolidate`, `/reflect` | P10 | AggregatingDistiller | Yes |

## Git 规范

### 分支命名

格式：`<type>/<kebab-case-description>`

- 前缀：`feat` / `fix` / `refactor` / `chore` / `docs` / `perf` / `test` / `build`
- description 用 kebab-case（小写 + 连字符），2-5 个词

```
feat/agent-runtime
fix/portal-state-leak
chore/upgrade-fastapi
```

禁止：无意义名称（`test123`、`temp`）、纯日期名称、中文 / 大写 / 下划线。

### 阶段分支工作流（P2 起生效）

每个 Phase 固定从 **master 最新** 建分支，验收通过后**合并回 master**，下一阶段再从 master 重新出发：

1. `git checkout master && git checkout -b feat/phase-N-xxx` — 永远从 master 最新建支，不从上一阶段的分支叠加
2. 阶段内所有工作在分支上完成（commit 原子化）
3. 验收通过后 fast-forward / merge 回 master
4. 分支合并后可删除；`.omo/` 状态随合并进入 master

例外：纯文档阶段（如 P1 命名）经用户确认可留在独立 docs 分支不合并。

### Commit Message

```
<type>(<scope>): <中文描述>
```

- type：feat、fix、docs、style、refactor、perf、test、chore、build
- subject：中文，祈使语态，50 字符内
- scope 选填（backend / portal / repo / ci 等）
- **禁止** `Co-authored-by` 署名行
- **禁止** 在 commit message 中使用 emoji

示例：

```
feat(backend): 新增用户表与软删除字段
fix(portal): 修复实例列表分页后状态丢失
chore(repo): 初始化根目录约定与启动脚本
```

### 自动提交

每完成一个单元性改动（独立可描述、可验证、可回滚）后必须立即 commit，禁止攒多个独立改动一起提交。

### 不要提交的内容

- `.env`、任何含密钥的文件
- `.venv/`、`node_modules/`、`__pycache__/`、`dist/`、`logs/`
- 业务真实数据（即使是测试 fixture）

`.gitignore` 已覆盖以上大部分场景，遇到遗漏请补 `.gitignore` 而不是 `git add -f`。

## 工作流

### 前置条件检查

启动任何流程前，先列出所有前置条件（依赖工具、`.env` 配置、端口占用、外部服务），缺一个就停下来告知用户怎么补。

### 排错原则

- **先查证再开口**：不确定的事情先查证（读文件、跑命令、看日志），查不到就说查不到
- **结论附依据**：每个关键结论必须说明依据（哪个文件、哪行代码、哪条命令输出）
- **禁止猜测性断言**：不凭"应该是这样"就下结论

### 破坏性操作

以下操作执行前必须逐项列出并获得用户明确确认：

- K8s 资源删除 / 替换
- 数据库 DROP / DELETE / TRUNCATE
- DNS / 域名变更
- `git push --force`、`git reset --hard`

## 仓库结构快查

```
.
├── cocoa-backend/        # Python 后端（pyproject.toml 在此）
├── cocoa-portal/         # React 前端（package.json 在此）
├── cocoa-artifacts/      # 镜像 / K8s 清单占位
├── .omo/                 # 计划、草稿、运行续接状态
├── .github/workflows/    # CI
├── .codegraph/           # 代码图索引（机器本地，已 git-ignore）
├── dev.sh                # 本地一键启动
├── AGENTS.md             # 本文件
├── README.md             # 项目说明
├── LICENSE               # Apache-2.0
└── .gitignore
```

进入对应子目录前先看其下的 `README.md`（若存在）。
