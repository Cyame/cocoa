# Cocoa 可观测性约定

> P3.5 落地的日志、事件审计、任务队列权威参考。与 `docs/api-architecture.md`（P3 API 约定）构成姊妹文档。
> 代码位置：`cocoa-backend/app/core/` —— 日志 `logging.py`、事件 `events.py` / `event_types.py`、队列 `queue.py`、中间件 `middleware/logging.py`、模型 `models/event.py`。

## 1. 日志约定

### 1.1 统一入口

所有日志统一走 loguru，禁止 `print()` 和 stdlib `logging.getLogger()` 直接输出。

```python
from loguru import logger

logger.info("Worker started", instance_id=instance_id)
logger.error("DB connection failed", host=host, port=port)
```

### 1.2 模块区分

在模块顶部用 `logger.bind(module=__name__)` 绑定模块名，方便按模块过滤。

```python
from loguru import logger

# 文件顶层：绑定当前模块名，该模块内所有日志行自动携带 module 字段
_logger = logger.bind(module=__name__)

async def process_task(task_id: str) -> None:
    _logger.info("Processing task", task_id=task_id)
```

### 1.3 request_id 贯通

`LoggingMiddleware`（`app/core/middleware/logging.py`）在每次请求内用 `logger.contextualize(request_id=...)` 包裹整个请求生命周期。context manager 退出后 extra 自动恢复，后续请求不会污染。

```python
# LoggingMiddleware.dispatch() 核心逻辑（已落地，无需手动调用）
with logger.contextualize(request_id=request_id):
    logger.info("http.request.start", method=request.method, path=request.url.path)
    response = await call_next(request)
    logger.info("http.request.end", status_code=response.status_code)
```

请求链路内所有日志（uvicorn、SQLAlchemy、auth、业务逻辑）自动携带 `request_id`，无需每行手动传参。

### 1.4 级别指引

| 级别 | 适用场景 | 示例 |
|------|---------|------|
| DEBUG | 开发调试信息、变量值、SQL 参数 | `logger.debug("Query params", params=params)` |
| INFO | 关键流程节点、请求起止、任务调度 | `logger.info("http.request.start", method=req.method)` |
| WARNING | 可恢复的异常、降级行为、重试 | `logger.warning("Rate limit approaching", remaining=5)` |
| ERROR | 操作失败、异常捕获、外部服务不可达 | `logger.error("DB commit failed", exc_info=True)` |

`logger.exception()` 是 `logger.error(exc_info=True)` 的快捷方式，二者等价。

### 1.5 prod JSON vs dev console

`configure_logging()`（`app/core/logging.py`）在 lifespan 启动时根据 `settings.ENV` 选择 sink：

- **dev**：彩色 console 输出到 stderr，human-readable 格式。
- **prod**：JSON 行输出到 stdout（`serialize=True`），每条日志一行 JSON，`extra` 字段扁平化在顶层。

```python
# app/core/logging.py 关键逻辑（已落地，无需手动干预）
if settings.ENV == "dev":
    logger.add(sys.stderr, level=settings.LOG_LEVEL, colorize=True,
               format="<green>{time:HH:mm:ss.SSS}</green> | "
                      "<level>{level: <8}</level> | "
                      "<cyan>{extra[request_id]}</cyan> | "
                      "<level>{message}</level>")
else:
    logger.add(sys.stdout, level=settings.LOG_LEVEL, serialize=True)
```

### 1.6 stdlib 桥接

`configure_logging()` 同时安装 `InterceptHandler`（`logging.Handler` 子类），将 uvicorn 和 SQLAlchemy 等 stdlib 日志路由到 loguru。所有日志行共享同一组 sink 和 `extra` 上下文。

---

## 2. 事件系统

### 2.1 事件模型

事件是一次性写入的审计记录，永不更新、永不删除（`deleted_at` 始终为 NULL）。模型定义在 `app/models/event.py`：

```python
class Event(BaseModel, Base):
    __tablename__ = "events"

    type: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
```

### 2.2 事件分类法常量

`app/core/event_types.py` 定义所有事件类型常量，命名规则：`<域>.<动作过去式>`。

| 常量 | 值 | 域 | 发射点 |
|------|-----|-----|--------|
| `SYSTEM_STARTUP` | `system.startup` | 系统生命周期 | P3.5（lifespan startup） |
| `SYSTEM_SHUTDOWN` | `system.shutdown` | 系统生命周期 | P3.5（lifespan shutdown） |
| `HARNESS_LOOP_STARTED` | `harness.loop_started` | 控制循环 | P8 落地 |
| `HARNESS_CHECKPOINT` | `harness.checkpoint` | 控制循环 | P8 落地 |
| `HARNESS_CONTINUATION_INJECTED` | `harness.continuation_injected` | 控制循环 | P8 落地 |
| `HARNESS_LOOP_STOPPED` | `harness.loop_stopped` | 控制循环 | P8 落地 |
| `HARNESS_BREAKER_TRIPPED` | `harness.breaker_tripped` | 控制循环 | P8 落地 |

harness 族常量已定义，但发射点（`emit()` 调用）留到 P8 落地。P3.5 仅发射 `system.startup` 和 `system.shutdown`。

### 2.3 emit() 用法

`emit()`（`app/core/events.py`）写入 Event 行并分发到匹配的 handler。调用方拥有事务边界，emit 只 flush 不 commit。

```python
from app.core.events import emit
from app.core.event_types import SYSTEM_STARTUP

async with get_session_factory()() as session:
    await emit(
        SYSTEM_STARTUP,
        actor_type="system",
        payload={"env": settings.ENV},
        session=session,
    )
    await session.commit()
```

**参数说明**：

| 参数 | 必填 | 说明 |
|------|------|------|
| `event_type` | 是 | 点分事件类型字符串，如 `"system.startup"` |
| `actor_type` | 是 | 触发者类型，`"system"` / `"user"` / `"agent"` |
| `actor_id` | 否 | 触发者 UUID |
| `resource_type` | 否 | 受影响资源类型 |
| `resource_id` | 否 | 受影响资源 UUID |
| `payload` | 否 | 自由格式 JSON-serializable 负载 |
| `request_id` | 否 | 关联 HTTP 请求 ID |
| `session` | 是 | 活跃的 AsyncSession |

### 2.4 handler 注册与 best-effort 语义

`register_handler(pattern, handler)` 注册事件监听器。`pattern` 支持 shell 风格通配符（`*`、`?`、`[seq]`）。handler 异常被捕获并记录，绝不传播到调用方。

```python
from app.core.events import register_handler

async def log_system_events(event, event_type, **kwargs):
    logger.info("System event", event_type=event_type)

# 注册通配 handler：匹配所有 system.* 事件
register_handler("system.*", log_system_events)
```

**handler 契约**：
- handler 在 `emit()` 调用方的事务内、commit 之前执行。handler 可访问同一事务内的未提交数据。
- handler 必须容忍回滚（phantom event），或在 handler 内使用 `after_commit` 事件推迟副作用。
- 一个 handler 抛异常不会阻塞其他 handler，也不会中断 `emit()` 的返回。

### 2.5 新增事件类型流程

1. 在 `app/core/event_types.py` 按 `<域>.<动作过去式>` 命名规则添加常量。
2. 在业务代码中调用 `emit(event_type, ...)` 发射事件。
3. 如需自动响应，调用 `register_handler(pattern, handler)` 注册监听器。

harness 族常量已预先定义，P8 直接使用即可。

---

## 3. TaskQueue

### 3.1 协议

`TaskQueue` 是 `typing.Protocol`（`app/core/queue.py`），定义四个方法，任何实现（内存 / Redis / Celery）只要满足协议即可替换。

| 方法 | 签名 | 说明 |
|------|------|------|
| `enqueue` | `async (task_name, *, delay, payload) -> str` | 调度任务，返回 UUID |
| `register_task` | `(task_name, handler)` | 注册任务处理器 |
| `start` | `async ()` | 启动 worker 协程 |
| `stop` | `async ()` | 优雅停止，排空当前任务 |

### 3.2 用法片段

```python
from app.core.queue import InMemoryTaskQueue

queue = InMemoryTaskQueue()

async def send_reminder(payload: dict) -> None:
    user_id = payload["user_id"]
    logger.info("Sending reminder", user_id=user_id)

queue.register_task("reminder.send", send_reminder)
await queue.start()

# 延迟 30 秒后执行
task_id = await queue.enqueue("reminder.send", delay=30.0, payload={"user_id": "u1"})
```

### 3.3 存根语义警告

当前 `InMemoryTaskQueue` 仅用于开发与测试：

- **进程重启丢任务**：队列在内存中，重启后所有未执行任务丢失。
- **单 worker**：只有一个 `asyncio.Task` 消费队列，无并发控制。
- **无持久化**：任务不落盘，不备份。

**生产环境务必替换为 Redis 实现**（见第 4 节）。

### 3.4 底层实现

`InMemoryTaskQueue` 内部使用 `asyncio.PriorityQueue`，按 `(run_at, seq)` 排序。`seq` 是单调递增计数器，保证同时间戳任务按入队顺序执行。worker 用 `asyncio.wait_for + asyncio.Event` 处理队首睡眠竞争：新任务入队时唤醒 worker，worker 重新评估队首截止时间。

---

## 4. 延后清单

以下能力在 P3.5 已设计接口/协议，但实现推迟到后续阶段。

| 能力 | 当前状态 | 目标阶段 | 说明 |
|------|---------|---------|------|
| Redis Streams 事件桥接 | `register_handler` 是桥接缝（seam），无需改代码 | P6 / P8 | 在 handler 层注册转发 handler 到 Redis Streams |
| Redis TaskQueue | `TaskQueue` 协议已有，`InMemoryTaskQueue` 仅开发用 | P6 / P8 | 持久化、多 worker、跨进程 |
| Langfuse LLM 可观测性 | 已批准，不集成进 FastAPI 后端 | P7 / P8 | agent runtime 层独立集成 |
| 事件查询 API | 无端点，事件表仅用于审计 | P9 | `GET /api/v1/events` 不分页不暴露 |
| Metrics / OpenTelemetry | 未定阶段 | TBD | 指标导出、trace 采样、dashboard 集成 |

**Redis Streams 桥接设计位置**：`app/core/events.py` 的 `register_handler` 是唯一接缝。P6/P8 只需注册一个 `"*"` 通配 handler 将事件转发到 Redis Streams，现有 `emit()` 调用方零改动。

**Redis TaskQueue 替换位置**：`app/core/queue.py` 的 `TaskQueue` 协议。P6/P8 实现一个 `RedisTaskQueue` 类，满足协议即可在 `app/main.py` lifespan 中替换 `InMemoryTaskQueue` 实例。

---

## 参考

- `docs/api-architecture.md` —— P3 API 约定（姊妹文档）
- `docs/domain-model.md` —— P2 核心域模型
- `app/core/logging.py` —— loguru 配置与 sink 选择
- `app/core/events.py` —— emit / register_handler
- `app/core/event_types.py` —— 事件分类法常量
- `app/core/queue.py` —— TaskQueue 协议与 InMemory 实现
- `app/core/middleware/logging.py` —— request_id 贯通
- `app/models/event.py` —— Event 审计模型