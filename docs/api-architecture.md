> **Pre-v4 reference**: Conflict with `.omo/evidence/audit-product-design.md` → audit wins. Awaiting v4 PRD rewrite.
>

# Eyot API 架构约定

> **Code rename pending (15d-rename wave)**: This doc describes target architecture (15d+). Current code uses old naming.

> P3 落地的后端 API 权威参考。P4-P10 所有业务端点必须遵循本文约定；调整约定时先改本文、再改代码。
> 代码位置：`cocoa-backend/app/` —— 路由 `app/api/`、中间件 `app/core/middleware/`、错误 `app/core/errors.py`、分页 `app/core/pagination.py`、OpenAPI `app/core/openapi.py`。

## 1. RESTful URL 规则集

### 1.1 版本边界（R1）

- 业务 API 全部挂在 `/api/v1/` 之下，由 `app/api/v1/router.py` 的 `api_router = APIRouter(prefix="/api/v1")` 统一聚合，再被 `app/main.py` 的 `app.include_router(api_router)` 挂载。
- 运维端点留在根路径、不版本化：`/health`（存活探针）、`/docs`、`/redoc`、`/openapi.json`。
- 仅破坏性变更（删字段、改语义、改状态码）才升 v2；新增字段、新增端点、新增可选查询参数均不升版本。

### 1.2 JSON 字段命名（R2）

snake_case 端到端：Pydantic 字段名即线上字段名，**无别名转换层**。请求体、响应体、查询参数全部 snake_case（如 `next_cursor`、`office_id`）。前端不得期望 camelCase 字段。

### 1.3 资源命名（R3）

- 复数 + kebab-case：`/api/v1/entities`、`/api/v1/base-classes`。
- 嵌套最多 2 层：`/api/v1/workspaces/{workspace_id}/entities` 合法；更深层级用查询参数拍平，如 `GET /api/v1/entities?workspace_id=<uuid>`。
- 路径参数统一 UUID：`/api/v1/instances/{instance_id}`，不暴露自增整数主键。

### 1.4 动作端点（R4）

资源上的非 CRUD 操作走 Stripe 风格动作端点：`POST /api/v1/instances/{instance_id}/archive`。不使用 `/{id}:action` 语法，也不为动作建独立动词 URL（禁止 `/archiveInstance`）。

### 1.5 HTTP 方法与状态码

| 场景 | 方法 | 成功状态码 | 说明 |
|------|------|-----------|------|
| 读单条 / 列表 | GET | 200 | 列表返回分页对象（见第 4 节） |
| 创建 | POST | 201 | 响应体为新建资源 |
| 全量 / 局部更新 | PUT / PATCH | 200 | 响应体为更新后资源 |
| 删除 | DELETE | 204 | 映射软删除（`deleted_at = now()`），无响应体 |
| 动作端点 | POST | 200 | 如 `/archive`、`/restore` |
| 资源不存在 | — | 404 | `NotFoundError` |
| 状态冲突（如重复键） | — | 409 | `ConflictError` |
| 请求体 / 参数校验失败 | — | 422 | `ValidationError` / `RequestValidationError` |
| 超出速率限制 | — | 429 | 携带 `Retry-After` 头 |
| 服务器内部错误 | — | 500 | `InternalError` / 兜底处理器 |

### 1.6 查询参数约定

- 过滤：按字段名直接过滤，`?status=active&workspace_id=<uuid>`。
- 排序：`?sort=-created_at`（`-` 前缀为降序），多字段逗号分隔 `?sort=-priority,created_at`。
- 分页：游标分页 `?limit=50&cursor=<opaque>`，偏移分页 `?limit=50&offset=0`（见第 4 节）。
- 时间戳：请求与响应中的时间一律 ISO 8601 UTC（如 `2026-07-25T08:30:00Z`）。

### 1.7 弃用策略

端点弃用分三步，全部通过响应头表达：

1. 宣告：`Deprecation: @<unix时间戳>`（RFC 9745，表示弃用生效时刻）+ `Link: <https://docs.cocoa.dev/api/deprecations/xxx>; rel="deprecation"`。
2. 限期：`Sunset: <HTTP-date>`（RFC 8594，如 `Sunset: Sat, 01 Nov 2026 00:00:00 GMT`），到期后端点移除。
3. 移除：再次请求返回 `410 Gone`，错误体仍为第 3 节标准信封。

### 1.8 URL 模式示例

| URL | 说明 |
|-----|------|
| `GET /health` | 运维探针，根路径不版本化 |
| `GET /api/v1/workspaces?limit=50&cursor=abc` | 列表 + 游标分页 |
| `POST /api/v1/workspaces` | 创建，返 201 |
| `GET /api/v1/workspaces/{workspace_id}` | 读单条 |
| `GET /api/v1/workspaces/{workspace_id}/entities` | 2 层嵌套列表 |
| `POST /api/v1/instances/{instance_id}/archive` | 动作端点 |
| `DELETE /api/v1/entities/{entity_id}` | 软删除，返 204 |

## 2. 中间件管道

### 2.1 管道图

每个请求自外向内依次穿过 5 个中间件，响应沿原路返回：

```
client
  │  request
  ▼
┌───────────────────────────────────────────────────────────┐
│ 1. RequestIDMiddleware   (app/core/middleware/request_id) │
│    uuid4 → request.state.request_id                       │
│    回显  → 响应头 X-Request-ID                            │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ 2. LoggingMiddleware      (app/core/middleware/      │  │
│  │    logging)                                          │  │
│  │    每个请求一条结构化 JSON 日志（含 request_id）     │  │
│  │    P3.5 引入                                          │  │
│  │  ┌───────────────────────────────────────────────┐  │  │
│  │  │ 3. CORSMiddleware    (fastapi.middleware.cors)│  │  │
│  │  │    dev: allow_origins/methods/headers = ["*"] │  │  │
│  │  │    P7 按环境收紧                               │  │  │
│  │  │  ┌─────────────────────────────────────────┐  │  │  │
│  │  │  │ 4. AuthMiddleware (app/core/middleware/ │  │  │  │
│  │  │  │    auth)                                │  │  │  │
│  │  │  │    解析 Authorization: Bearer <token>    │  │  │  │
│  │  │  │    → request.state.token / .user_id      │  │  │  │
│  │  │  │    P3 存根只提取不校验；P4 接入真实 JWT   │  │  │  │
│  │  │  │  ┌─────────────────────────────────────┐  │  │  │  │
│  │  │  │  │ 5. RateLimitMiddleware             │  │  │  │  │
│  │  │  │  │  (app/core/middleware/rate_limit)  │  │  │  │  │
│  │  │  │  │  固定窗口 100 次/60s，按客户端 IP   │  │  │  │  │
│  │  │  │  │  仅计数 /api/*；/health、/docs 豁免 │  │  │  │  │
│  │  │  │  │  超限 → 429 + Retry-After          │  │  │  │  │
│  │  │  │  │       + X-RateLimit-Remaining      │  │  │  │  │
│  │  │  │  │  内存存根；P8 换 Redis              │  │  │  │  │
│  │  │  │  │                ↓                   │  │  │  │  │
│  │  │  │  │        APIRouter → endpoint        │  │  │  │  │
│  │  │  │  └─────────────────────────────────────┘  │  │  │  │
│  │  │  └─────────────────────────────────────────┘  │  │  │
│  │  └───────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

### 2.2 注册顺序反转（Starlette 栈语义）

Starlette 的 `add_middleware` 把每个中间件插入栈顶（`user_middleware.insert(0, ...)`），因此**注册调用顺序与执行顺序相反**：最后注册的最外层、最先执行。`app/main.py` 中的实际注册代码（注释即契约，改动时必须同步更新）：

```python
# Registration order is REVERSED vs execution order because Starlette inserts each
# middleware at stack position 0 (`user_middleware.insert(0, ...)`), so the LAST
# add_middleware call ends up outermost and executes FIRST.
# Execution order (outer → inner): RequestID → Logging → CORS → Auth → RateLimit.
# Registration call order:          RateLimit → Auth → CORS → Logging → RequestID.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Dev default; tighten per-environment in P7.
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)  # P3.5 — sits between CORS and RequestID.
app.add_middleware(RequestIDMiddleware)
```

> LoggingMiddleware 在 P3.5 加入（位于 CORS 与 RequestID 之间）——为每个请求生成结构化 JSON 日志条目，注入 request_id。

新增中间件时按期望的执行位置**反向**插入注册序列，并在块上方注释中更新两行顺序说明。

## 3. 错误格式规范

### 3.1 标准错误信封

所有 API 错误（含原生 404/405、422 校验失败、429、500 兜底）统一返回 5 字段信封：

```json
{
  "error_code": "instance.not_found",
  "message_key": "errors.instance.not_found",
  "message": "Instance 'foo' not found",
  "details": null,
  "request_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
}
```

- `error_code`：稳定机器标识（小写点分级），客户端据此分支处理。
- `message_key`：i18n 查表键，命名规范见 `AGENTS.md` 的 i18n 一节。
- `message`：人类可读兜底文本。
- `details`：结构化上下文（如 422 的 `{"errors": [...]}`），无则为 `null`。
- `request_id`：由异常处理器从 `request.state.request_id` 注入，与 `X-Request-ID` 响应头一致。

### 3.2 错误类一览（`app/core/errors.py`）

| 类 | status_code | 用途 |
|----|------------|------|
| `EyotError` | 500（构造时可覆盖） | 全部 Eyot 错误的基类 |
| `NotFoundError` | 404 | 资源不存在 |
| `ValidationError` | 422 | 领域层校验失败（非请求 schema 校验） |
| `UnauthorizedError` | 401 | 缺失或无效凭证 |
| `ForbiddenError` | 403 | 已认证但无权限 |
| `ConflictError` | 409 | 状态冲突，如重复键 |
| `InternalError` | 500 | 预期内的服务端失败 |

框架级异常的映射（`app/main.py` 四个全局处理器保证信封一致）：

| 异常来源 | 映射结果 |
|----------|----------|
| `EyotError` 及其子类 | 按 `exc.status_code` 序列化为信封 |
| `StarletteHTTPException`（路由未匹配、405 等） | `error_code = "http.{status}"`，**透传 `exc.headers`**（如 405 的 `Allow`） |
| `RequestValidationError`（Pydantic 请求校验） | 422 + `error_code = "validation_error"` + `details.errors` |
| `RateLimitMiddleware` 超限 | 429 + `error_code = "rate_limit_exceeded"` + `Retry-After` 头 |
| 未捕获 `Exception` | 500 + `error_code = "internal_error"`；`details.traceback` 仅 `ENV=dev` 暴露 |

### 3.3 抛出错误（业务代码用法）

```python
from app.core.errors import NotFoundError

@router.get("/instances/{instance_id}")
async def get_instance(instance_id: str, db: DB) -> InstanceOut:
    instance = await db.get(Instance, instance_id)
    if instance is None or instance.deleted_at is not None:
        raise NotFoundError(
            "instance.not_found",
            "errors.instance.not_found",
            f"Instance '{instance_id}' not found",
        )
    return instance
```

不要在业务代码里 `raise HTTPException(...)` 或手写 `JSONResponse(status_code=404, ...)`——那会绕过统一信封。中间件内部（如 RateLimit 的 429）是例外：`EyotError` 处理器挂在内层 `ExceptionMiddleware`，捕获不到中间件里抛出的异常，因此中间件必须自行构造标准信封 JSON。

## 4. 分页标准

### 4.1 两种模式（`app/core/pagination.py`）

```python
class CursorPage(BaseModel, Generic[T]):
    """Cursor-based pagination response."""
    items: list[T]
    next_cursor: str | None = None
    total: int | None = None


class OffsetPage(BaseModel, Generic[T]):
    """Offset-based pagination response."""
    items: list[T]
    offset: int
    limit: int
    total: int
```

| 维度 | 游标分页（默认） | 偏移分页（备选） |
|------|----------------|-----------------|
| 适用集合 | 大表、追加频繁（消息、日志、memory entries） | 小表、需要总数和跳页的管理台列表 |
| 并发写入稳定性 | 稳定（基于值比较，不受插入位移影响） | 可能重复 / 漏行 |
| 响应字段 | `items` + `next_cursor`（+ 可选 `total`） | `items` + `offset` + `limit` + `total` |
| 请求参数 | `?limit=50&cursor=<opaque>` | `?limit=50&offset=0` |

### 4.2 请求与响应约定

- `limit`：默认 50，范围 1-200（`get_pagination_params` 中 `Query(50, ge=1, le=200)`）。
- 游标为不透明字符串：服务端用 `str(value)` 编码，客户端不得解析其内容；`next_cursor` 为 `null` 表示已到末页。
- 游标分页响应应同时给出 `Link` 头（RFC 8288），便于客户端不解析 body 即可翻页：

```
Link: </api/v1/entities?limit=50&cursor=2026-07-25T08%3A30%3A00Z>; rel="next"
```

- 偏移分页不返 `Link` 头，总数由 body 的 `total` 字段提供。

### 4.3 服务端调用

`paginate_offset`：传入的 query **不得预设** `LIMIT` / `OFFSET`（会污染 count），函数内部追加：

```python
from sqlalchemy import select

from app.core.pagination import OffsetPage, paginate_offset
from app.models.employee import Employee

async def list_entities(db: DB, offset: int, limit: int) -> OffsetPage[Employee]:
    query = select(Employee).where(Employee.deleted_at.is_(None))
    return await paginate_offset(db, query, offset=offset, limit=limit)
```

`paginate_cursor`：传入的 query **必须已含** `.order_by(cursor_field)` 升序；`decoder` 把游标字符串解析回字段类型（如 `datetime.fromisoformat`）：

```python
from datetime import datetime

from app.core.pagination import CursorPage, paginate_cursor
from app.models.memory import MemoryEntry

async def list_memory(db: DB, cursor: str | None, limit: int) -> CursorPage[MemoryEntry]:
    query = (
        select(MemoryEntry)
        .where(MemoryEntry.deleted_at.is_(None))
        .order_by(MemoryEntry.created_at)  # 升序，契约要求
    )
    return await paginate_cursor(
        db, query, MemoryEntry.created_at, limit,
        decoder=datetime.fromisoformat,
        cursor=cursor,
    )
```

两个函数都是纯 SQLAlchemy 适配，不依赖 FastAPI 请求对象，可在服务层直接测试。

## 5. 依赖注入

`app/api/deps.py` 提供三个共享依赖，每个都附带 `Annotated` 类型别名，端点签名直接用别名：

| 依赖 | 别名 | 作用 |
|------|------|------|
| `get_db` | `DB` | 从 session 工厂产出 `AsyncSession`，请求结束自动关闭 |
| `get_current_user` | `CurrentUserDep` | 认证用户。P3 存根：`ENV=dev` 时一律视为超级管理员；其他环境抛 401，待 P4 接入真实校验（只换函数体，`CurrentUser` 模型不变） |
| `get_pagination_params` | `PaginationParams` | 解析 `limit`（1-200，默认 50）、`cursor`、`offset`（默认 0）为 `dict` |

```python
from app.api.deps import DB, CurrentUserDep, PaginationParams
from app.core.errors import ForbiddenError

@router.get("/workspaces/{workspace_id}/entities")
async def list_workspace_entities(
    workspace_id: str,
    db: DB,
    current_user: CurrentUserDep,
    page: PaginationParams,
) -> OffsetPage[Employee]:
    if not current_user.is_super_admin:
        raise ForbiddenError(
            "workspace.forbidden",
            "errors.workspace.forbidden",
            "Only super-admins may list workspace entities",
        )
    query = (
        select(Employee)
        .where(Employee.deleted_at.is_(None))
    )
    return await paginate_offset(db, query, offset=page["offset"], limit=page["limit"])
```

`CurrentUser` 模型（`app/schemas/auth.py`）是 P4-P10 的认证契约：`user_id: str`、`is_super_admin: bool`、`token: str | None`。新依赖一律在 `app/api/deps.py` 注册并导出 `Annotated` 别名，禁止在端点里手写 `Depends(get_db)` 长链。

## 6. OpenAPI 规范

- 文档入口（根路径、不版本化）：Swagger UI `/docs`，ReDoc `/redoc`，schema `/openapi.json`。
- 应用元数据在 `app/main.py` 的 `FastAPI(...)` 构造中：`title="Eyot API"`、`version="1.0.0"`、`swagger_ui_parameters={"defaultModelsExpandDepth": -1}`（默认折叠 model 区，保持端点列表可读）。
- 标签组织（`openapi_tags`）：`Health`、`Auth`、`BaseClasses`、`Entities`、`Workspaces`、`Instances`、`Messaging`、`Blackboard`、`Learning`（共 9 个）。每个子路由文件用 `APIRouter(prefix="/entities", tags=["Entities"])` 对齐其一，禁止自造新标签名。
- 标准错误响应：`app/core/openapi.py` 的 `STANDARD_ERROR_RESPONSES` 定义了 401 / 403 / 404 / 422 / 500 五个状态码的信封示例。每个业务路由注册一次：

```python
from fastapi import APIRouter

from app.core.openapi import add_error_responses

router = APIRouter(prefix="/entities", tags=["Entities"])
add_error_responses(router)  # 一次性为整个路由登记 401/403/404/422/500

@router.get("/{entity_id}")
async def get_entity(entity_id: str):
    ...
```

这样生成的 OpenAPI schema 对每个端点都会广告统一的错误信封形状，客户端 SDK 可据此生成错误类型。

## 7. 快速参考（复制粘贴模板）

### 7.1 新业务路由骨架（`app/api/v1/widgets.py`）

```python
"""Widget API routes (template for P4-P10 resources)."""

from fastapi import APIRouter, Response, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUserDep, PaginationParams
from app.core.errors import NotFoundError
from app.core.openapi import add_error_responses
from app.core.pagination import OffsetPage, paginate_offset

router = APIRouter(prefix="/widgets", tags=["Workspaces"])
add_error_responses(router)


@router.get("", response_model=OffsetPage[WidgetOut])
async def list_widgets(db: DB, page: PaginationParams) -> OffsetPage[Widget]:
    query = select(Widget).where(Widget.deleted_at.is_(None))
    return await paginate_offset(db, query, offset=page["offset"], limit=page["limit"])


@router.get("/{widget_id}", response_model=WidgetOut)
async def get_widget(widget_id: str, db: DB) -> Widget:
    widget = await db.get(Widget, widget_id)
    if widget is None or widget.deleted_at is not None:
        raise NotFoundError(
            "widget.not_found", "errors.widget.not_found", f"Widget '{widget_id}' not found"
        )
    return widget


@router.post("", response_model=WidgetOut, status_code=status.HTTP_201_CREATED)
async def create_widget(body: WidgetCreate, db: DB, current_user: CurrentUserDep) -> Widget:
    widget = Widget(**body.model_dump())
    db.add(widget)
    await db.commit()
    return widget


@router.delete("/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_widget(widget_id: str, db: DB, current_user: CurrentUserDep) -> Response:
    widget = await get_widget(widget_id, db)  # 复用 404 逻辑
    widget.soft_delete()
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{widget_id}/archive", response_model=WidgetOut)
async def archive_widget(widget_id: str, db: DB, current_user: CurrentUserDep) -> Widget:
    widget = await get_widget(widget_id, db)
    widget.is_archived = True
    await db.commit()
    return widget
```

然后在 `app/api/v1/router.py` 中 `api_router.include_router(router)` 挂入 `/api/v1/widgets`。

### 7.2 抛错误

```python
from app.core.errors import ConflictError, NotFoundError

raise NotFoundError("workspace.not_found", "errors.workspace.not_found", f"Workspace '{slug}' not found")
raise ConflictError("workspace.slug_taken", "errors.workspace.slug_taken", f"Slug '{slug}' is taken")
```

### 7.3 分页调用

```python
from app.core.pagination import paginate_cursor, paginate_offset

# 偏移分页（需要总数 / 跳页）
page = await paginate_offset(db, query, offset=0, limit=50)

# 游标分页（默认；query 必须已 .order_by(cursor_field) 升序）
page = await paginate_cursor(db, query, Model.created_at, 50,
                             decoder=datetime.fromisoformat, cursor=cursor)
```

### 7.4 认证依赖注入

```python
from app.api.deps import CurrentUserDep

@router.post("/admin-only")
async def admin_only(current_user: CurrentUserDep) -> dict[str, str]:
    return {"user_id": current_user.user_id}
```
