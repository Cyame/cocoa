# PRD-v2 Append — 世界 Provider 与眷族绑定

> **Status**: design-locked (append-fix)  
> **Parent**: [`docs/prd-v2.md`](prd-v2.md) §14（Onboarding）、§16（Organization）、§9.4（InstanceProviderConfig）  
> **Date**: 2026-07-29  
> **Scope**: 补齐世界级 LLM Provider（models.dev 全量预设 + 可持久化自定义端点），以及眷族创建时的 Provider / Model 下拉绑定。本文件为产品 SoT；实现见 [`.omo/plans/prd-v2-append-provider.md`](../.omo/plans/prd-v2-append-provider.md)。

---

## §A0 问题与口径

### A0.1 现状缺口

| 层 | PRD-v2 期望 | 现状 |
|---|---|---|
| Org 级 Provider 表 / API | §16 世界「智能系统」CRUD + 连通性测试 | **缺失**（仅有 `InstanceProviderConfig`，无 API、runtime 未读） |
| `/organization` UI | Provider 表格 + Modal | Stub（`organization.providerHint`） |
| models.dev | 世界级预设源 | `ModelCatalog` 内部缓存可用，**未暴露**为预设目录 API |
| 眷族创建 Provider / Model | 下拉 | Step2 **自由文本**；payload 发 `runtime_config`，后端只认 `config_override` → **静默丢失** |
| SSL / Gemini / 独立 models URL | — | `LLMProviderConfig` / `LLMClient` 未覆盖 |

### A0.2 锁定口径（相对早期草稿）

**禁止**：自定义端点 `/models` 失败后静默 fallback 到 models.dev / allowlist / 手填伪装成「同一目录」。

**必须**：

1. **models.dev 是预设源** — `https://models.dev/api.json` 中的 **全部 provider** 作为世界级 Catalog 预设（名称、默认 `api`、模型目录、npm→请求格式映射）。
2. **自定义端点可持久化** — OpenAI / OpenAI-compatible / Anthropic / Gemini，含 SSL、独立 models 接口；与 Catalog 启用项同属 **Organization（世界）** 注册表。
3. **眷族创建** 只从世界 **已启用** Provider 下拉绑定；模型列表按该行 `origin` 分流（catalog → models.dev；custom → 其 models URL）。

---

## §A1 世界级双源

```
models.dev api.json（全量预设）
        │ 启用 + api_key_ref
        ▼
OrganizationProvider（世界注册表）  ◄── 新建自定义端点（可持久化）
        │ 眷族下拉（仅 enabled=true）
        ▼
Entity.config_override.provider_id + model
        │ spawn
        ▼
LLMClient（verify_ssl + request_format）
```

| 来源 | 如何进入世界注册表 | 模型列表 SoT |
|---|---|---|
| **Catalog preset** | `/organization`「从 models.dev 启用」→ 物化一行 `origin=catalog`，`catalog_provider_id=<models.dev key>` | **始终** models.dev 该 provider 的 `models`（服务端缓存 TTL 600s）。不以远端 `/models` 成败改道。 |
| **Custom** | 「+ 自定义端点」→ `origin=custom`，四格式之一 + `base_url` 等 | `inherit` → `GET {base_url}/models`；`separate` → 见 §A2.3。失败 → **报错** + UI 仍可用 `default_model` 手选/手填；**不**改去 models.dev。 |

**Builtin 硬编码列表**（现有 `ModelCatalog._BUILTIN_FALLBACK`）：仅当 **models.dev 整站不可达** 时作为 Catalog 预设目录的离线降级，不是「某个自定义端点失败」的路径。

---

## §A2 数据模型

### A2.1 新表 `organization_providers`

软删除 + Partial Unique Index（活跃行）。归属 `organizations.id`。

| 列 | 类型 | 约束 / 说明 |
|---|---|---|
| `id` | UUID PK | |
| `organization_id` | FK → organizations | NOT NULL |
| `origin` | enum | `catalog` \| `custom` |
| `catalog_provider_id` | str \| null | models.dev provider key；`origin=catalog` 必填；`(organization_id, catalog_provider_id)` partial unique where `deleted_at IS NULL AND origin='catalog'` |
| `name` | str | 展示名；catalog 默认同步 models.dev `name`，可改 |
| `slug` | str | org 内 partial unique（`deleted_at IS NULL`） |
| `request_format` | enum | `completion` \| `response` \| `anthropic` \| `gemini` |
| `base_url` | str \| null | catalog 默认取 models.dev `api`；custom / 网关覆盖可改 |
| `api_key_ref` | str | env/secret 引用，**禁止存明文密钥**；启用后用于调用时必填 |
| `default_model` | str | NOT NULL |
| `models_allowlist` | JSONB \| null | 可选字符串数组；空/null = 不限制下拉 |
| `verify_ssl` | bool | 默认 `true`；`false` = 不校验 TLS（自签/内网） |
| `models_endpoint_mode` | enum | `inherit` \| `separate`；主要服务 custom；catalog UI 可折叠默认 `inherit` |
| `models_base_url` | str \| null | `separate` 时必填 |
| `enabled` | bool | 默认 `true`；**仅 `enabled=true` 出现在眷族 Provider 下拉** |
| `last_test_status` | enum \| null | `ok` \| `error` \| null |
| `last_tested_at` | timestamptz \| null | |
| `last_test_detail` | JSONB \| null | 延迟 ms / 错误摘要 |
| `created_at` / `updated_at` / `deleted_at` | | BaseModel 惯例 |

### A2.2 `request_format` → 运行时

| `request_format` | 调用形态 | 旧 `ProviderType` 对应 |
|---|---|---|
| `completion` | OpenAI-compatible `chat.completions` | `openai-compatible` / `custom` |
| `response` | OpenAI `responses.create` | `openai-responses` |
| `anthropic` | Anthropic `messages.create` | `anthropic` |
| `gemini` | Google Gemini `generateContent` | **新增** |

Catalog 启用时：由 models.dev 条目的 `npm` / `api` **推断**默认 `request_format`，用户可覆盖。

自定义创建对话框 **固定四选一**（产品标签 → 默认 format）：

| UI 标签 | 默认 `request_format` | 说明 |
|---|---|---|
| OpenAI | `completion`（可改 `response`） | 官方语义，可改 `base_url` |
| OpenAI-compatible | `completion` | 任意通常以 `/v1` 结尾的网关 |
| Anthropic | `anthropic` | |
| Gemini | `gemini` | |

### A2.3 Models 接口解析（仅 custom / 显式 separate）

1. `models_endpoint_mode = inherit`：`GET {base_url.rstrip('/')}/models`  
2. `models_endpoint_mode = separate`：  
   - 若 `models_base_url` path 已含 `/models`（或实现约定的完整 list URL）→ **原样 GET**  
   - 否则 → `GET {models_base_url.rstrip('/')}/models`  
3. 请求使用该行的 `verify_ssl` 与 `api_key_ref` 解析出的密钥（Authorization / x-api-key 按 format）。  
4. 失败：返回 API 错误包络；Portal 展示错误 + 保留 `default_model` 选项；**禁止**改拉 models.dev。

### A2.4 与既有表关系

| 表 / 字段 | 本 append 后的职责 |
|---|---|
| `organization_providers` | **世界唯一录入与绑定源** |
| `Entity.config_override` | 存 `{ provider_id, model, system_prompt?, max_tokens?, temperature? }` |
| `InstanceProviderConfig` | 实例级覆盖；spawn 时可从 Entity 绑定物化；**不**开世界 UI |
| BaseClass.manifest `provider` / `provider_config` | 神职默认；无世界绑定时的继承源 |

实现波次须统一 manifest 键名读取（`provider` vs `provider_config`）为 overlay 单一路径；本 append 不要求迁移历史数据以外的硬切。

---

## §A3 API

约定：`/api/v1/`、snake_case、错误 `{error_code, message_key, message, details, request_id}`。  
写操作：`require_super_admin`（与现 `PATCH /organizations/default` 一致）。  
读 Catalog / 世界注册表 / model-catalog：登录用户（眷族下拉需要）。

### A3.1 Provider Catalog（models.dev 预设，非 DB）

| Method | Path | 说明 |
|---|---|---|
| `GET` | `/provider-catalog` | 全量预设：`id`, `name`, `api`, `inferred_request_format`, `model_count`, `doc?`；`?q=` 过滤 name/id |
| `GET` | `/provider-catalog/{catalog_provider_id}/models` | 该预设下模型列表（缓存） |

整站不可达：返回 builtin 降级子集 + 响应头或 body 字段 `degraded: true`（实现选定一种，文档化）。

### A3.2 世界注册表

挂在 default Organization 下（单租户兼容；多 org 远期改为 `/{org_id}`）：

| Method | Path | 说明 |
|---|---|---|
| `GET` | `/organizations/default/providers` | 列表；`?enabled=` 可选 |
| `POST` | `/organizations/default/providers` | 启用 catalog 或新建 custom |
| `GET` | `/organizations/default/providers/{id}` | 详情（`api_key_ref` 可掩码策略：读回完整 ref 名，非密钥） |
| `PATCH` | `/organizations/default/providers/{id}` | 更新；可 `enabled=false` 停用 |
| `DELETE` | `/organizations/default/providers/{id}` | 软删除 |
| `POST` | `/organizations/default/providers/{id}/test` | 最小连通性探测；写回 `last_test_*` |

**POST body（catalog 启用）**

```json
{
  "origin": "catalog",
  "catalog_provider_id": "openai",
  "api_key_ref": "OPENAI_API_KEY",
  "name": null,
  "base_url": null,
  "default_model": null,
  "request_format": null,
  "verify_ssl": true
}
```

`null` 字段：服务端用 models.dev 默认填充。同一 org 重复启用同一 `catalog_provider_id` → `409`（或幂等返回已有行——实现锁 **409 + message_key**）。

**POST body（custom）**

```json
{
  "origin": "custom",
  "name": "内部网关",
  "slug": "corp-gateway",
  "request_format": "completion",
  "base_url": "https://llm.example.com/v1",
  "api_key_ref": "CORP_LLM_KEY",
  "default_model": "gpt-4o-mini",
  "models_allowlist": null,
  "verify_ssl": false,
  "models_endpoint_mode": "separate",
  "models_base_url": "https://llm.example.com/v1/models"
}
```

### A3.3 Model catalog（按世界 Provider 分流）

| Method | Path | 说明 |
|---|---|---|
| `GET` | `/model-catalog?provider_id={organization_provider_id}` | 按该行 `origin` 分流；应用 `models_allowlist`；可选 `?q=` |

---

## §A4 世界设置 UX（`/organization`）

取代 PRD-v2 §16.1–§16.2 的字段表；页面形态仍为 AppShell + 全宽 Canvas。

**Page Header**：标题「智能系统」+ 描述 + Stats（「已启用 N · Catalog 预设 M · 自定义 K」）+ 「+ 自定义端点」（需超管）。

### A4.1 Catalog 预设区

- 数据：`GET /provider-catalog`  
- 行：name、id（mono）、模型数、推断 format chip、默认 api 截断、状态（未启用 / 已启用）  
- 「启用」→ Modal：`api_key_ref`（必填）、可选覆盖 `base_url` / `default_model` / `request_format` / `verify_ssl` → `POST …/providers`  
- 已启用：跳转或高亮下方注册表行；可「停用」

### A4.2 已保存 Provider 区

列：origin chip（catalog / custom）+ `request_format` + `base_url`（mono truncate）+ `default_model` + SSL（开/关）+ models 模式 + 测试状态 + 操作（测试 / 编辑 / 停用或删除）。

**自定义 Modal 字段**：name、slug、四格式、`api_key_ref`、`base_url`、`default_model`、`models_allowlist`、`verify_ssl`、`models_endpoint_mode` +（separate 时）`models_base_url`。

**权限**：无超管 → 只读列表；CTA 换「联系管理员启用 Provider」。

**空态（注册表为空）**：引导启用 Catalog 或新建自定义。

---

## §A5 眷族创建（Onboarding）

对齐 PRD-v1 Step2 下拉语义，收紧 PRD-v2 §14：

| 控件 | 行为 |
|---|---|
| 智能系统 | `<select>` ← `GET …/providers?enabled=true`；首项「继承神职默认」（`provider_id=null`） |
| 模型 | `<select>` ← `GET /model-catalog?provider_id=`；含「使用 default_model」；加载中 / 失败 retry；custom 失败时仍列出 `default_model` |
| 空注册表 | 仅「继承神职默认」+ 文案链到 `/organization` |

**禁止**在本 Modal 新建 Provider。

### A5.1 Payload（硬切）

`POST /entities` body 使用 `config_override`，**删除**被忽略的 `runtime_config.provider` 字符串路径：

```json
{
  "name": "…",
  "slug": "…",
  "rank": "intern",
  "base_class_id": "…",
  "namespace_id": "…",
  "display_name": "…",
  "config_override": {
    "provider_id": "<uuid>|null",
    "model": "<id>|null",
    "system_prompt": null,
    "max_tokens": 1024,
    "temperature": 0.7
  }
}
```

字段名与后端 `EntityCreate` 对齐；若当前 API 仍用 `preset_slug` 等别名，实现波次一并收敛到 PRD-v2 字段，不在 append 另开兼容层。

---

## §A6 解析优先级（spawn / LLM 调用）

1. `InstanceProviderConfig`（若该 Instance 存在覆盖行）  
2. `Entity.config_override.provider_id` → `organization_providers`（须 `enabled` 且未软删）  
3. BaseClass.manifest 的 provider / provider_config  
4. 进程环境默认（如 `OPENAI_API_KEY` + 默认 model）

`LLMClient` 构造必须传入：`request_format`、`base_url`、`api_key`（由 ref 解析）、`default_model`、`verify_ssl`。httpx / SDK `verify=` 与 `verify_ssl` 对齐。

---

## §A7 非目标

- 眷族 / Namespace 页内联「新建 Provider」  
- 明文 API Key 入库  
- 自定义 models 列表失败时静默改用 models.dev  
- Contracts / capability-market / NodePort / 部署脚本变更（除非实现波次单独要求）  
- 多 Organization 路径参数化（保留 `/organizations/default/…`）

---

## §A8 验收 Checklist

- [ ] `/organization` 可见 **models.dev 全量 provider 预设**，可启用并持久化到 `organization_providers`  
- [ ] 可新建并保存四类自定义端点（含 `verify_ssl`、独立 models URL）  
- [ ] 眷族创建 Provider / Model 均为下拉；选项 = 世界 `enabled=true` 行  
- [ ] Catalog 绑定的模型列表来自 models.dev；Custom 来自其 models URL  
- [ ] Custom `/models` 失败时 UI 报错，仍可用 `default_model`，**不**静默切 models.dev  
- [ ] 创建后 DB 可见 `config_override.provider_id`；旧自由文本 / `runtime_config` 误投路径删除  
- [ ] `POST …/providers/{id}/test` 更新 `last_test_*`；spawn / 调用尊重 `verify_ssl` + `request_format`（含 gemini）  
- [ ] 后端测试覆盖 catalog 启用 409、model-catalog 分流、软删除过滤；Portal tsc / lint / vitest 绿  

---

## §A9 实现波次指针

详见 [`.omo/plans/prd-v2-append-provider.md`](../.omo/plans/prd-v2-append-provider.md)：

| Wave | 内容 |
|---|---|
| P | 本 append + prd-v2 指针（本文档波次） |
| F1 | 表 + API + ModelCatalog 分流 + LLMClient SSL/gemini |
| F2 | OrganizationPage + onboarding 双下拉 + i18n |
| F3 | spawn 解析 + test 端点联调 + orbstack 冒烟 |
