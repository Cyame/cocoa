# PRD-v3.4 — 次元契印、引入眷族与迷失者生命周期

> **Status**: implemented  
> **Date**: 2026-07-30  
> **Product version**: **3.4.0**  
> **Parent**: [`prd-v3.md`](prd-v3.md) / [`prd-v3-post`](../.omo/plans/prd-v3-post.md)  
> **Glossary**: [`terminology.md`](terminology.md) + [`metaphor-name-table.md`](metaphor-name-table.md)

---

## TL;DR

- **契印** 只存在于 **次元**（`NamespaceContract` 真表）。
- 空间层不再说契印：在场真人叫 **觉醒者**，运行中的 Instance 叫 **迷失者**（浅识者+深潜者通称）。
- 管理单位是 **眷族**；空间内 **引入眷族** → 生成迷失者（pod）。
- 迷失者生命周期 ≤ 空间；删空间级联软删迷失者与其拓扑位。
- `@slug` 寻址绑眷族 → **同空间同眷族最多 1 个活跃迷失者**（永久产品不变量）。
- 初期硬切：无旧数据回填；可重置 orbstack DB。

---

## §1 名词锁

| 概念 | Backend | 产品名 | 层 |
|------|---------|--------|-----|
| Namespace ↔ User | `NamespaceContract` | **契印** | 仅次元 |
| Membership(`user_id`) | Workspace 在场 | **觉醒者** | 仅空间 |
| `Instance` | pod | **迷失者** | 仅空间（生命周期≤空间） |
| Membership(`instance_id`) | 拓扑位 | 归迷失者 UI | 空间 |
| `Entity` | 身份+记忆 | **眷族** | 次元持久 |

空间卡片 / IDE：`xx 觉醒者` · `xx 迷失者`。

英文 UI：`Directors`（觉醒者）、`Lost Ones`（迷失者）、`Contracts`（契印）。

---

## §2 数据模型

### 2.1 `namespace_contracts`

- `namespace_id`, `user_id`, `role` (`owner|editor|viewer`), `permissions` JSONB
- Soft-delete；partial unique `(namespace_id, user_id) WHERE deleted_at IS NULL`
- 无 backfill

### 2.2 `instances`

- Partial unique `(workspace_id, entity_id) WHERE deleted_at IS NULL`
- `workspace_id` NOT NULL（已有）

### 2.3 Workspace 删除级联（soft-delete）

顺序：Instances（+K8s best-effort）→ Memberships → Passages → CentralHub/Cerebellum/Vault → Workspace。  
不级联 Entity / NamespaceContract。

---

## §3 API

| 能力 | 端点 |
|------|------|
| 契印 CRUD | `/api/v1/namespaces/{id}/contracts` |
| 引入眷族 | `POST /api/v1/workspaces/{id}/introduce-entity` `{entity_id}` → 409 if present |
| 建空间/拉人 | ensure NamespaceContract → user Membership |
| `POST /instances` | 保留；强制 unique；Portal 不从次元发起召唤 |

---

## §4 Portal IA

| 入口 | 行为 |
|------|------|
| 次元 · 契印 | NamespaceContract 真列表（`/namespaces/{id}/contracts`） |
| 次元 · 空间卡 | 觉醒者 / 迷失者计数 |
| 次元 · 化身 tab | **保留「化身」名**（跨空间只读聚合，弱化）；无「选空间召唤」主 CTA。**不**改称迷失者 |
| 空间 | **引入眷族**；tab：觉醒者 / 迷失者（迷失者只在空间层用此名） |
| 眷族详情 | 迷失者只读 + 前往空间引入 |

---

## §5 不变量

1. `@slug` → Entity；同空间同眷族 ≤ 1 迷失者。  
2. 契印只在次元说。  
3. 迷失者唯一主创建路径 = 空间「引入眷族」。

---

## §6 非目标（推迟）

旧数据回填、主视觉/头像、session-engine/Tunnel/Voice、Membership XOR 拆表、Namespace 整树级联、同空间多分身。
