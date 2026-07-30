# PRD-v3 — 世界 Provider、隐式 System 中枢与蒸馏 UX

> **Status**: design-locked (awaiting implementation wave)  
> **Date**: 2026-07-30  
> **基线**: [`prd-v2.md`](prd-v2.md)（已落地）+ [`prd-v2-append-provider.md`](prd-v2-append-provider.md)（设计已锁、实现待做）+ [`.omo/drafts/baseclass-tags-and-empty-workspace.md`](../.omo/drafts/baseclass-tags-and-empty-workspace.md)  
> **Intake 问答账本**: [`.omo/drafts/prd-v3-intake.md`](../.omo/drafts/prd-v3-intake.md)  
> **运维非目标**: kubectl / NodePort / 暴露方式不进本 PRD（`AGENTS.md` Rule 5 — 只动 `orbstack`）

---

## TL;DR

v3 把「世界智能系统」从 stub 做成可配置的 Provider 注册表与默认绑定；引入**隐式 System 中枢**（不调度、无独立页），在创建眷族时按名称/文案辅助生成 description；厘清**主脑**默认供应商（世界 fallback，空间可覆盖）；重做**晋升 / 炼化**双 Modal（晋升模式：**回魂** | **派生**；炼化：仅铸新神职）。允许并强调**空空间**创建（仅主脑即可）。头像切换、主视觉换皮、空 IDE 深度打磨留后续刀。

---

## §1 范围

### 1.1 MVP 必须交付

| ID | 主题 |
|----|------|
| V3-P1 | 世界 Provider 全实现（吸收 append：models.dev 预设 + 自定义 + SSL / `request_format` / 独立 models URL） |
| V3-P2 | `/organization` Provider UI + 「设为默认」子面板 + 被绑定方页面可改默认 |
| V3-P3 | 眷族创建：Provider/Model 下拉 + `config_override` 落库；description **生成/优化**（System 中枢） |
| V3-P4 | System 中枢默认 Provider（世界设置可选）；未配置则辅助按钮置灰 |
| V3-P5 | 主脑默认 Provider：**世界 fallback + per-Workspace 覆盖**（创建后可改，创建时不强制） |
| V3-P6 | 晋升 Modal（**回魂** \| **派生**）+ 炼化 Modal（仅新建）；Namespace / Workspace **各自独立入口**（先选对象再开 Modal） |
| V3-P7 | tags 正式化（含 `ultraworker`）+ `cerebellum-baseclass` / `internal` **API 级隐藏** |
| V3-P8 | **空空间**：创建空间交互明确「可空、仅主脑」；不要求先召唤眷族 |

### 1.2 明确不做（后续刀）

| ID | 主题 |
|----|------|
| Later-A | 用户/眷族预设头像切换 UI、上传/截图 |
| Later-B | 神职候选图挂卡片 + 主视觉整站换皮 |
| Later-C | 空 Workspace IDE 深度打磨、onboarding 神职预选增强 |
| Later-D | Capability / skill 自动撰写与优化（System 中枢能力扩展） |
| Later-E | System 中枢进入调度流 / 拓扑节点 / 独立中枢页 |

### 1.3 非目标

- 明文存 API Key  
- 自定义 `/models` 失败静默改道 models.dev  
- 炼化写回源眷族或影响旗下化身  
- 运维暴露方案（NodePort 等）

---

## §2 概念：两层中枢

```
System 中枢（隐式，Organization 级）
  · 不入调度 / 不入拓扑 / 无独立产品页
  · 用途：平台辅助（v3 = 眷族 description 生成/优化）
  · 绑定：世界设置中的「系统中枢供应商」= OrganizationProvider + model

主脑 / Cerebellum（Workspace 级，已有 1:1）
  · Workspace 内中枢：巡检、脑干调度默认执行人等（既有职责）
  · 绑定：世界「主脑默认」fallback + Workspace 可覆盖 provider/model
  · 创建空间时不强制配置；创建后在主脑/空间设置中可改
```

| | System 中枢 | 主脑 |
|--|-------------|------|
| 作用域 | Organization / 平台 | 单个 Workspace |
| 调度 | 否 | 是（空间内） |
| UI 页 | 无；仅设置项 + 功能按钮 | 主脑视图 / 空间设置 |
| v3 LLM 用途 | description 辅助 | 沿用既有 + 可配默认供应商 |

---

## §3 世界 Provider 与默认绑定

完整传输层规格继承 [`prd-v2-append-provider.md`](prd-v2-append-provider.md)。v3 **增量**：

### 3.1 默认绑定目标（三类）

每个绑定存 **`provider_id` + `model`**（一对默认值）。业务侧使用时 **两者仍可改**，默认只提供初值。

| 目标 | 存储建议 | 基数 |
|------|----------|------|
| 神职默认 | `base_class_provider_defaults` 或 BaseClass.manifest 旁表：`(base_class_id, provider_id, model)` | **一对多**：同一 Provider 行可成为多个神职的默认 |
| System 中枢默认 | Organization 级单例：`system_hub_provider_id` + `system_hub_model` | 0..1 |
| 主脑世界默认 | Organization 级：`cerebellum_default_provider_id` + `cerebellum_default_model` | 0..1（fallback） |
| 主脑空间覆盖 | Workspace 或 CerebellumAgent 上：`provider_id` + `model` 可空 = 继承世界默认 | per-Workspace |

### 3.2 「设为默认」UX（Q5 = B + 被绑定方可改）

**Provider 侧（世界设置 Provider 列表 / 编辑）**

1. 动作：「设为默认…」打开**子面板**（非三个平铺裸按钮）。  
2. 子面板用 **radio** 选目标类型：  
   - 神职默认 → 多选神职列表（可一对多）+ 确认 model（预填该 Provider 的 `default_model`，可改）  
   - 系统中枢默认 → 确认 model  
   - 主脑默认（世界 fallback）→ 确认 model  
3. 保存后列表可显示「已作为：密士·暗行·中枢·主脑…」chips。

**被绑定方页面（必须可变更同一字段）**

| 页面 | 字段 |
|------|------|
| 神职详情 `/base-classes/:slug` | 默认 Provider + Model 下拉（来自世界已启用列表） |
| 世界设置「系统中枢」菜单项 | 中枢 Provider + Model；可清空 |
| Workspace / 主脑设置 | 主脑 Provider + Model；空 = 继承世界主脑默认；创建后可改 |

未配置 System 中枢时：所有依赖中枢的按钮置灰（见 §4）。

### 3.3 眷族创建绑定

- Provider / Model：**下拉**（仅 `enabled` 世界 Provider）。  
- 初值：若所选神职有默认绑定 → 预填；否则「继承神职默认」为空则引导世界设置。  
- Payload：`config_override.provider_id` + `model`（**禁止**再发被忽略的 `runtime_config.provider` 字符串）。

---

## §4 System 中枢 — description 辅助（Q6）

### 4.1 出现位置

创建眷族流程（Onboarding Step2 或等价表单）的 **description** 字段旁。

### 4.2 单一动态按钮

文案随状态切换（**一个按钮，不是两个**）：

| 条件 | 按钮文案 | 行为 |
|------|----------|------|
| description **非空** | 「优化当前描述」 | 以现有 description（+ 名称）为输入，中枢改写后写回字段 |
| description **为空** 且名称已填 | 「生成当前描述」 | 按名称生成 description 写回 |
| 名称为空 | **置灰** | hover：「请先填入眷族名称」 |
| System 中枢未配置 | **置灰** | hover：「请先在世界设置中配置系统中枢供应商」 |

### 4.3 反馈

- 进行中：按钮/字段区 **转圈** loading，禁止重复点。  
- 失败：**inline** error（字段下），可重试。  
- 成功：写入可编辑 textarea，用户可再改。

### 4.4 非目标

- Capability / skill 自动撰写（Later-D）  
- 自动在无按钮时静默调用中枢

---

## §5 主脑默认供应商（Q2 = M2）

1. 世界设置可设「主脑默认 Provider + model」（fallback）。  
2. 每个 Workspace 主脑可覆盖；**创建空间不弹强制配置**。  
3. 解析顺序：Workspace 覆盖 → 世界主脑默认 → 环境/硬编码兜底。  
4. 空空间合法：创建后仅 CentralHub + CerebellumAgent，无眷族/化身也可进入 IDE。

---

## §6 晋升与炼化 UX（Q3 / Q4 / Q7）

### 6.1 正式命名

| 口语 | **产品正式名** | 后端 `mode` | Hover 说明 |
|------|----------------|-------------|------------|
| 影响当前 | **回魂** | `update` | 将化身经验写回**当前眷族**；其下化身在**重启后**同步新配置 |
| 创建新 | **派生** | `fork` | 从化身**派生新眷族**；源眷族与源化身不变 |
| 炼化 | **炼化**（铸新神职） | （仅新建，无 mode） | 仅创建**新神职**；不影响任何现有眷族或化身 |

UI 主文案用「回魂 / 派生」；旁加 `ⓘ` hover。后端 **不要** 用 `promote_update` 一类带晋升前缀的枚举——就用 `update` / `fork`。

### 6.2 入口（Ns1 + Workspace 同理）

- **Namespace**：眷族表 / 化身相关行操作「回魂 / 派生 / 炼化」——**先有对象，再开 Modal**（无「空白总入口」先开再选）。  
- **Workspace**：化身浮窗、眷族/记忆相关卡片同行操作，同样先选对象。  
- **两个独立 Modal**（不合成蒸馏工作台 tab）。

### 6.3 晋升 Modal（`PromoteModal`）

**模式选择**（radio + 正式名 + hover）：

- 回魂  
- 派生  

**共用**

- 源化身 / 源眷族只读摘要  
- 能力候选多选（来自化身 runtime / 记忆蒸馏候选）  
- system_prompt 预览，可编辑  
- 主 CTA：随模式「确认回魂」/「确认派生」

**回魂专有**

- 影响面说明（固定区块）：「将更新眷族 {name}。当前下属化身 N 个，**重启后**同步。」  
- 无需新 slug

**派生专有**

- 新眷族 display name、slug（必填）  
- 说明：源眷族与化身保持不变  

**成功**

- 回魂：关闭 Modal；提示「已回魂；请重启相关化身」  
- 派生：关闭；可链到新眷族详情  

### 6.4 炼化 Modal（`TransmuteModal`）

- 新神职 display name、slug  
- 记忆 kind 过滤  
- manifest 预览（v3：只读预览即可；微调可后续）  
- **二次确认说明**（非阻断式额外 Modal，用确认区文案即可）：  
  「炼化仅创建新神职，**不会影响**任何现有眷族或其化身。」  
- CTA：「确认炼化」

### 6.5 语义铁律

| 动作 | mode | 写源 Entity | 写新 Entity | 写新 BaseClass | 旗下化身 |
|------|------|-------------|-------------|----------------|----------|
| 回魂 | `update` | Yes | No | No | 重启后吃新 `migration_hash` |
| 派生 | `fork` | No | Yes | No | 源化身不变；不自动迁移挂载 |
| 炼化 | — | No | No | Yes | 无影响 |

---

## §7 空空间（V3-P8）

- Namespace「创建空间」：名称 + slug；文案明确「可先建空空间，主脑自动就位」。  
- 成功后可「进入空间」；不强制 onboarding。  
- 召唤眷族仍为独立 CTA。

---

## §8 Tags 与内部神职（V3-P7）

- `BaseClass.tags`：自由字符串数组；筛选 UI 动态并集。  
- 暗行 `an-xing` 主 tag：`ultraworker`（可兼 `execute`）。  
- `cerebellum-baseclass` 及 tag `internal`/`system`：**list/market/onboarding API 默认排除**；仅系统内部引用。

---

## §9 页面与路由影响

| 表面 | 变化 |
|------|------|
| `/organization` | Provider 双区（catalog + 已保存）；「设为默认…」子面板；「系统中枢」「主脑默认」菜单/区块 |
| `/base-classes/:slug` | 默认可编辑 Provider + model |
| `/namespaces` | 创建空空间；行内晋升/炼化入口；召唤眷族 |
| `/workspaces/:id` | 主脑设置覆盖；行内/浮窗晋升炼化；可空态 |
| Onboarding | 下拉 Provider/Model；description 动态按钮 |

无新独立「System 中枢页」。

---

## §10 API 增量摘要（实现时对齐 `api-architecture.md`）

在 append 已列 Provider CRUD / catalog / model-catalog 之上增加：

| Method | Path（示意） | 说明 |
|--------|--------------|------|
| `POST` | `/organizations/default/providers/{id}/set-default` | body：`target=base_class\|system_hub\|cerebellum` + 细节 |
| `GET/PATCH` | `/organizations/default/system-hub` | 中枢 provider/model，可清空 |
| `GET/PATCH` | `/organizations/default/cerebellum-defaults` | 世界主脑 fallback |
| `PATCH` | `/workspaces/{id}/cerebellum` 或 `/central-hubs/{id}/cerebellum` | 空间覆盖 |
| `POST` | `/system-hub/generate-description` | `{ name, description? }` → `{ description }`；未配置中枢 → 4xx + message_key |
| `POST` | `/learning/instances/{id}/promote` | body 含 `mode: update\|fork` + 字段 |
| `POST` | `/learning/entities/{id}/transmute` | 仅新建神职 |

错误包络不变。写默认 / 中枢配置：超管；description 生成：登录用户。

---

## §11 验收 Checklist

- [ ] 世界可启用 models.dev + 自定义 Provider；SSL / 四格式 / 独立 models URL 可用  
- [ ] 「设为默认…」子面板可设神职（一对多）/ 中枢 / 主脑世界默认；神职页与中枢/主脑设置可改同一绑定  
- [ ] 眷族创建下拉落库 `config_override`；description 按钮三态（生成/优化/置灰）+ loading + inline error  
- [ ] 未配中枢时按钮置灰且 hover 正确  
- [ ] 空空间可创建并进入；主脑默认可后改  
- [ ] 回魂（`update`）改源 Entity；派生（`fork`）新建 Entity；炼化仅新神职且确认文案可见  
- [ ] Namespace 与 Workspace 均可先选对象再开对应 Modal  
- [ ] internal 神职不出现在市场/onboarding；暗行可按 `ultraworker` 筛选  
- [ ] 无新 System 中枢独立路由；capability 自动撰写未实现（有意）

---

## §12 实现波次建议

| Wave | 内容 |
|------|------|
| V3-A | Provider 表/API/LLMClient（append）+ 三类默认绑定 API |
| V3-B | Organization / 神职 / 主脑设置 UI + 眷族下拉 + description 中枢调用 |
| V3-C | 晋升 `update`/`fork` + 炼化 Modal + ns/ws 入口 + 重启同步约定 |
| V3-D | tags/internal 过滤 + 空空间文案验收；orbstack 冒烟 |

---

*Locked from intake Q1–Q8 (2026-07-30). Formal names: 回魂 / 派生； backend `mode`: `update` / `fork`.*
