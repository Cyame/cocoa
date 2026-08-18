# Eyot System Roadmap & Blueprint

> **Status**: Living document. Canonical project roadmap + system goal blueprint.
> **Authority**: Supersedes archived pre-v4 roadmaps under `.omo/plans/archive/`.
> **Design SoT (2026-08-01)**: `.omo/evidence/audit-product-design.md` (v3.5.x design correction; decisions D1–D11).
> **Implementation wave**: **v4** — `.omo/plans/v4-roadmap.md` + `v4-0`…`v4-10`（v4.10 已完成；v4.9.5 closeout 完成）。
> **Next generation**: **v5** — 完整世代（更名 → 定义 → UIUX → 视觉）；SoT `.omo/evidence/v5-rename-decisions.md` + 执行总图 `.omo/plans/0x-roadmap.md`。
> **Archived PRDs**: `docs/archive/` (prd-v1 … prd-v3.4.1). Subsystem `docs/*-system.md` = pre-v4 reference; conflicts → audit wins.
> **Naming**: `docs/terminology.md` + `docs/metaphor-name-table.md`（**v5 命名基线**：大陆/区域/生境/始祖/血脉/后裔/5 动物；15d 版归档于 `docs/archive/`）。
> **Last revision**: 2026-08-07（v5 完整世代立项 + 命名 SoT 闭环）。

---

## 0. How to use this doc

| Reader | Read first | Then |
|---|---|---|
| Planner / new session | `.omo/evidence/audit-product-design.md` + `.omo/plans/v4-roadmap.md` + this §0.1 / §5 | `audit-cross-reference.md` · `audit-conclusions.md` |
| Worker implementing a wave | Active `v4-N-*.md` plan + §6 hard rules | `audit-implementation.md` (as-is baseline) |
| Reviewer | `audit-cross-reference.md` vs target design | Closure gate `v4-9-closure-gate.md` |

**Do not** treat `docs/archive/*` or `.omo/plans/archive/*` as current direction.

### 0.1 Active wave — 0.5.3 视觉波（= v5.3）

当前版本轨 **0.x**（pre-1.0，正式 tag 从 1.0 起）。已交付切片：**0.4.x ≈ v4 功能收口**（v4.0–v4.10，已归档）、**0.5.0 = v5.0 命名**、**0.5.1 = v5.1 定义**、**0.5.2 = v5.2 UIUX**（均已实现落地）。

**当前唯一 active 切片 = 0.5.3（v5.3 视觉波）**：

| Slice | Plan | Goal |
|---|---|---|
| 0.5.3 | `0-5-3-visual.md` | 视觉 SoT + `@theme` token + dark/light 双主题 + 壳层现代化 + 5 始祖头像资产 + Avatar 体系 + 密度/空态/一致性 |

0.5.3 之后（远期，§5.4 / §7）：Capability hub assist、Session engine v2（multimodal day-1）、Gene LLM real、nodeskclaw parity 候选（Voice / channels / multi-runtime…）。总图见 `.omo/plans/0x-roadmap.md`。

---

## 1. System goal blueprint

### 1.1 One-sentence product

**Eyot is a K8s-native multi-agent control studio**: human directors summon reusable AI role templates (神职 / BaseClass), specialize them into scenario identities (眷族 / Entity), materialize running pods (化身 / Instance), observe them on a topology canvas, and distill runtime experience back into reusable capability and new roles.

### 1.2 Why it exists

Traditional chat agents reset every session. Eyot closes three loops that chat tools leave open:

| Loop | Without Eyot | With Eyot |
|---|---|---|
| **Identity** | Disposable reply | BaseClass → Entity → Instance (L1 / L2 / L3 progressive specialization) |
| **Memory** | Context window only | Append-only Memory per Entity + promote / transmute |
| **Collaboration** | 1:1 flat chat | Shared Workspace + Passage near-neighbor messaging + CentralHub + visual Topology |

Inherited from `nodeskclaw`, rebuilt lighter and vision-first. Loop engineering (Boulder / circuit breakers / notepad) is borrowed from `oh-my-openagent` (pin tags; do not trust its unstable `dev` tree) — that family (senpi / oh-my-openagent / oh-my-pi) is the **Workspace-layer** peer Eyot aims to surpass in flexibility and observability. Each **化身 (Instance)** is driven by a sandboxed **pi** agent runtime (React runtime optional, less preferred) — never by Senpi CLI as the Instance driver.

### 1.3 What Eyot is / is not

| Is | Is not |
|---|---|
| Multi-agent **control plane** with visual portal | Generic chatbot / Copilot clone |
| Workspace ≈ more flexible / observable senpi · oh-my-openagent · oh-my-pi | Senpi CLI as the per-Instance agent driver |
| Per-化身 **pi** sandboxed runtime (React optional) | Equating "pi runtime" with "Senpi CLI" |
| Persistent Entity memory + distillation market | Stateless prompt playground |
| Near-neighbor Passage topology + glow live-status | Flat group-chat bus |
| K8s-native Instance deploy (orbstack for live test) | Desktop-only toy runtime |
| Single-tenant default with multi-tenant **schema reserve** (PRD-v2) | Full nodeskclaw 6-registry platform copy |
| | No-code builder / RAG vector KB (deferred) |
| | Voice gateway day-1 (deferred) |

### 1.4 Ontological stack (locked)

Three orthogonal axes — never conflate:

```
职阶 Lab Rank (互斥, 1 per being)
  真人 → 觉醒者 (director)
  AI   → 浅识者 (intern) | 深潜者 (researcher)   # frozen at Entity create

能力 Capabilities (多选, 双侧不同表)
  真人 → user_genes (permission packs: can_*)
  AI   → ai_genes (unified manifest JSONB; no kind enum; no workflow-gene)

知识 Knowledge (Instance-only concept)
  Embedded in Instance.runtime_config.knowledge {env, files}
  Not a DB table; dies with Instance
```

Agent progressive specialization:

```
L1 BaseClass (神职)     System-scoped, business-AGNOSTIC role archetype
L2 Entity    (眷族)     Namespace-scoped, scenario-SPECIFIC (system_prompt + config_override)
L3 Instance  (化身)     Workspace-scoped, business-CONCRETE (runtime_config + knowledge + pod)
```

Capability lifecycle — **two independent chains** (PRD-v2 clarification; not a single "四级跳"):

```
Chain A (content):  Memory ──reap──▶ Capability ──compose──▶ ai_gene
Chain B (identity): Instance ──promote──▶ Entity ──transmute──▶ BaseClass
```

Tenant hierarchy (PRD-v2):

```
System (logical control plane — NOT a DB table)
  └── Organization (世界)     tenant boundary
        └── Namespace (次元)  **scenario** partition (NOT env); Entity lives here
              └── Workspace (空间)  concrete workstream in that scenario; Instance + Membership + Passage + CentralHub(+CerebellumAgent) + Vault live here
```

Example: Namespace `coding` vs `social-media`; within social-media, Workspaces `wechat-official` / `xiaohongshu`. Entity binds Namespace so scenario identity/memory spans those Workspaces.

Single-tenant default forever valid: `1 Org → 1 Namespace → 1 Workspace`, empty start.

**Vault (v2)**: DB KV (`vault_entries`, optional inline value) is enough; object store (MinIO/S3) is deferred — see PRD-v2 §8.3.

**CentralHub**: every Workspace hub includes exactly one built-in **CerebellumAgent** (central intelligence; not a topology Membership).

### 1.5 Portal surface (target)

| Surface | Route | Role |
|---|---|---|
| Login / Register | `/login` | Auth; first user → super_admin + admin-gene |
| Namespace hub | `/namespaces` (+ 6 tabs) | Default post-login; Workspace grid / 神职市场 / 契印 / 眷族 / 能力市场 / 调试 |
| Workspace IDE | `/workspaces/:id` | Sidebar + Topology/Membership/Instance/Memory tabs + Composer + StatusBar |
| BaseClass detail | `/base-classes/:slug` | Full-screen 神职 (overview / commands / derived entities / memory agg) |
| Organization | `/organization` | Provider configs (v2 scope) |
| Forbidden | `/403` | Missing permission_keys |
| Onboarding | Modal | 3-step: pick 神职 → name+rank → provider+knowledge |

Topology is the flagship: SVG nodes + glow(`loop_status`) + Select/Connect/Move + Passage particle animation. CorridorNode dropped — Membership↔Membership only.

### 1.6 Runtime spine (already largely built)

**Two layers — never conflate** (locked 2026-07-30):

| Layer | Peer / driver | Eyot role |
|---|---|---|
| **Workspace control plane** | senpi · oh-my-openagent · oh-my-pi (Eyot = more flexible + more observable evolution) | Portal + Harness Supervisor + Passage + CentralHub + deploy + observability |
| **Instance agent runtime** | **pi** (sandboxed; preferred). React runtime optional | Each 化身 pod runs under pi; Entity overlay → AgentConfig → pi |

| Layer | Mechanism | Status vs PRD-v2 |
|---|---|---|
| Harness | Supervisor + 4 breakers + control commands | Done (P8); keep (Workspace layer) |
| Instance driver | **pi via Host RPC + Tunnel WS** | Done (PRD-v3.5): `eyot-instance-host` + `WS /api/v1/tunnel/connect`; stub fallback when offline |
| Deploy | 9-step K8s pipeline + DeployRecord + SSE | Done (P11–P15a); keep |
| LLM | 4 providers + ModelCatalog + LLMDistiller | Done (P14a); keep |
| Messaging | Passage-gated near-neighbor + 4 command families | Done (P5/P8/P10); rename Corridor→Passage pending |
| CentralHub | 4 brain regions (Fornix + 3 new in P15f) | Partial → complete under v2 polish |
| Learning | reap / promote / transmute / compose endpoints | P15f scaffold; align to PRD-v2 two-chain rules |
| Multitenancy | Org / Namespace tables + Entity.namespace_id | **PRD-v2 implementation wave** |
| Genes | user_genes + ai_genes unified schema | **PRD-v2 implementation wave** |

---

## 2. Iteration model — PRD-driven

Eyot no longer plans primarily as open-ended "P-N feature waves". After foundation (P0–P15b) and naming lock (P15d), **product truth lives in PRD documents under `docs/`**, and engineering waves implement a named PRD slice.

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Lock naming / ontology     (P15d — done)                 │
│ 2. Write PRD (interaction + data decisions)                 │
│ 3. Write /approve execution plan (.omo/plans/)              │
│ 4. Implement on feature branch from main                    │
│ 5. Tests + evidence                                         │
│ 6. Merge main                                               │
│ 7. Deploy orbstack (mandatory — §6)                         │
│ 8. Human inspect live cluster → next PRD delta or polish    │
└─────────────────────────────────────────────────────────────┘
```

| Artifact | Role | Mutability |
|---|---|---|
| `docs/prd-vN.md` | Product + UX + schema decisions for a generation | Append / revise only with explicit decision; never silent drift |
| `docs/roadmap.md` (this file) | System blueprint + wave status + queue | Living |
| `docs/*.md` subsystem docs | Engineering contracts (API, harness, …) | Update when code lands |
| `.omo/plans/phase-*.md` | Executable worker plans for one wave | Immutable after merge → archive |
| `.omo/evidence/*` | Audits, capability maps, deploy state | Append; archive snapshots |
| `.omo/drafts/*` | In-flight design before PRD/plan lock | Archive when superseded |

**PRD / design generations**:

| Gen | Intent | Status |
|---|---|---|
| **v1–v3.4.1** | Historical product slices | **Archived** → `docs/archive/` |
| **v3.5.x design correction** | audit-review + D1–D11 → `audit-product-design.md` | **Done** (docs) |
| **v4** | Functional closure (schema, tenant, knowledge, clone, harness collab, …) | **Done**（v4.0–v4.10 + v4.9.5 closeout 质量审查通过 2026-08-08）— `.omo/plans/v4-*.md` |
| **v5** | 完整世代：更名（山海+生物世界观）+ 定义（5 始祖/6 subagent/镜像体系）+ UIUX + 视觉（原 3.6） | **Done（v5.0 命名 / v5.1 定义 / v5.2 UIUX 已实现落地，等价 0.5.0–0.5.2）**；唯一剩余 **v5.3 视觉波 = 0.5.3**（当前 active，待实施）— `.omo/evidence/v5-rename-decisions.md` + `.omo/plans/0x-roadmap.md` |
| **Later** | Session-engine-v2 multimodal, Voice, … | §7 far queue |

Code identifiers follow 15d names (`Workspace`, `Entity`, `Passage`, `BaseClass`) — **v5 世代只改 UI 显示名与 5 动物 slug，代码名/DB/API 仍保持 15d**（见 `.omo/evidence/v5-rename-decisions.md`）。Pre-v2 names remain only in alembic history.

---

## 3. Current state snapshot (2026-07-29)

### 3.1 Shipped foundation (P0 – P15f)

| Band | What landed |
|---|---|
| **P0–P10** | Domain models, REST, events, 6→evolving presets, messaging, blackboard/hub, K8s scaffolds, harness, portal+topology, learning protocol |
| **P11–P14a** | Real K8s client/builder/deploy service, LLM providers, LLMDistiller |
| **P15a–b** | Orbstack live deploy + portal onboarding/i18n/nginx; Persistent Fix Policy |
| **P15c–d** | Doc restructure; naming system + product spec (36 decisions) |
| **P15e** | `docs/prd-v1.md` interaction PRD |
| **P15f** | Brain-region tables + 3-layer market tables + 5 learning actions + outdated/restart + onboarding/topology/entity UI slices |

### 3.2 Honest gaps vs PRD-v2

These are the structural deltas the next wave must close (not polish):

1. **Tenant tables**: Organization / Namespace not first-class; Entity still Office/Workspace-scoped in code, not `namespace_id`.
2. **Entity overlay**: missing `system_prompt` + `config_override` (oh-my-openagent AgentOverrideConfigSchema).
3. **Genes**: `ai_genes` may still carry kind enum from v1; v2 requires **unified manifest, no kind, no workflow-gene**; `user_genes` (+ N:N) not fully wired as permission source of truth.
4. **BaseClass ownership**: System-global pool (no `org_id`) vs preset table semantics still mixed with legacy `EmployeePreset`.
5. **Portal IA**: login default still office-centric; target default `/namespaces` + VSCode IDE shell per PRD-v2 §10–§13.
6. **CapabilityMarket**: PRD-v2 treats market as **conceptual view**; P15f introduced a concrete table — reconcile in v2 plan (view vs table) without breaking P15f actions.
7. **Naming debt**: Office/Employee/Corridor/CorridorNode still in codepaths; CorridorNode drop incomplete.

### 3.3 Live test environment

Orbstack namespace `eyot` is the **persistent human inspection environment**. See `.omo/evidence/orbstack-operations.md` + `.omo/evidence/eyot-deployment-state.md`. Every implementation wave that changes backend/portal/deploy **must** end with `scripts/deploy-to-orbstack.sh` (§6).

---

## 4. Target architecture (PRD-v2 condensed)

Authoritative detail: 设计 SoT `.omo/evidence/audit-product-design.md`（PRD-v2 已归档至 `docs/archive/prd-v2.md`）。This section is the blueprint digest only.

### 4.1 Data

- **18 core tables** + **2 N:N** (`user_user_genes`, `base_class_ai_genes`) + conceptual System / Knowledge / CapabilityMarket (+ Event audit table outside the 18).
- Soft delete everywhere; Partial Unique Indexes only.
- Membership exclusive-FK (user XOR instance); Passage M↔M only.
- Memory append-only (no `updated_at`).

### 4.2 Runtime compatibility

Entity overlays serialize toward **pi AgentConfig** (schema family shared with oh-my-openagent `AgentOverrideConfigSchema` overlay; pin `oh-my-openagent` tag, e.g. v4.19.2, for overlay field names only). The **Workspace** control plane (Harness / Boulder / Portal) is Eyot's evolution of senpi · oh-my-openagent · oh-my-pi. Each **Instance** is driven by **pi**, not by Senpi CLI. Boulder remains the control-plane engine; workflow-gene is rejected — orchestration stays in Harness.

### 4.3 Default deployment shape

```
orbstack K8s
  namespace eyot
    eyot-backend  : API + harness + deploy controller
    eyot-portal   : React operator UI
    eyot-postgres : tenant DB for the live env
```

Local pytest continues to use `eyot_test_*` clones on `local-pgvector` — never `eyot_dev` on that shared instance.

---

## 5. Wave status & queue

### 5.1 Completed (archive only)

Full history: `.omo/plans/archive/` + `.omo/plans/archive/eyot-v2-roadmap.md` (pre-PRD era status table) + `.omo/plans/archive/phase-15-foundation-roadmap.md` (P15 foundation notes).

| Milestone | Outcome |
|---|---|
| P0–P14a | Core studio + K8s + LLM |
| P15a–b | Orbstack + onboarding foundation |
| P15d | Naming + product ontology lock |
| P15e | PRD-v1 written |
| P15f | PRD-v1 must-have implementation |
| PRD-v2 generation | `docs/prd-v2.md` decision-complete |
| **PRD-v2 impl** | Hard-cut tenant schema + genes + two-chain learning + portal IDE — `.omo/plans/prd-v2-implementation.md` |

### 5.2 Version track (locked 2026-07-31)

| Track | Intent | Plan |
|---|---|---|
| **3.5.x / 3.6** | 主流程闭环 + 纯视觉 UI 大重构（历史轨，已被 v4/v5 取代）| `.omo/plans/archive/product-version-track-3-5-3-6.md` |
| **4.x** | v4 功能收口（已完成 v4.0–v4.10 + v4.9.5 closeout，等价 0.4.x 前置）| `.omo/plans/v4-roadmap.md`（已归档） |
| **5.x** | v5 完整世代：更名 → 定义 → UIUX → 视觉（已交付到 0.5.2；等价 0.5.x 前身）| `.omo/plans/0x-roadmap.md`（已归档） |
| **0.x (Eyot)** | **2026-08-17 Cocoa → Eyot 重置后唯一 active 版本轨**：pre-1.0 **0.x**，正式 tag 从 **1.0** 起；MINOR 每完成一个切片 +1。已交付切片等价映射：**0.4.x ≈ v4 功能收口 / 0.5.0=v5.0 命名 / 0.5.1=v5.1 定义 / 0.5.2=v5.2 UIUX**；**当前 active = 0.5.3（v5.3 视觉波）**。alembic 压平为单一 schema 基线，默认数据由 app 层 idempotent seeder 注入 | `.omo/plans/0x-roadmap.md`（0.x 总图） |

**Working agreement:** 主功能仍有不通处与未修正项，随产品迭代逐步设计与变更；**不做**「先大改 UI 再通主流程」（v4 已闭环主流程；v5 视觉波在命名/定义/UIUX 之后）。

> **历史轨**：3.5.x / 3.6 为文档纠偏与纯视觉轨；4.x/5.x 为已实施世代（等价 0.4.x / 0.5.0–0.5.2，命名与抽象沿用至今）；**当前唯一 active 版本轨为 Eyot 0.x pre-1.0**（2026-08-17 Cocoa → Eyot 重置，见 §5.2 表格末行与 `RELEASE_NOTES.md`）。`v4-roadmap.md` / `0x-roadmap.md` 已归档为历史实现参考；0.x 总图见 `.omo/plans/0x-roadmap.md`。

### 5.3 Now（历史轨 3.5.x 遗留；当前 v4 收尾 + v5 世代见 §5.2）

| Slot | Title | Spec / Plan | Notes |
|---|---|---|---|
| **3.5 track** | Main-flow closed loop | `archive/product-version-track-3-5-3-6.md` + `archive/main-flow-remainder-tracking.md` | Product **3.5.2+**; iterative QA-driven slices |
| **PRD-v3.5 baseline** | Tunnel + pi Host 真连接 | `.omo/plans/prd-v3-5-tunnel-pi.md` | Landed; Host chat + offline stub |
| **PRD-v3.4.1** | Composer `@`/`/` + stream + deploy-existing | `docs/prd-v3.4.1.md` | Verified; passage gate + transcript continue in 3.5.x |

### 5.4 Near backlog (after / alongside 3.5.x closure)

| Slot | Theme | Source |
|---|---|---|
| **PRD-v3.4.2** | 全神职基础 gene + capability（空间会话 / 拓扑邻接说话） | 建在 3.5 tunnel/pi 上；仍属 3.5.x 行为闭环 |
| Cerebellum business | 未连线 `@` 转小脑的真实业务 | Stub exists; design in later 3.5.x slice |
| **0.5.3 视觉波**（= v5.3，原 3.6/5.3）| Portal / Composer / Topology visual overhaul（`@theme` token + dark/light + 壳层现代化 + 5 始祖头像资产 + Avatar 体系 + 密度/空态） | **当前 active 切片**（0.5.2 已交付后唯一未实施波）→ `.omo/plans/0-5-3-visual.md` |
| Avatar presets UI | 用户/血脉预设头像切换 | → **0.5.3**（原 Later-A，并入 v5.3 Avatar 体系） |
| Visual + 始祖图 | 主视觉换皮、候选图挂卡片 | → **0.5.3**（原 Later-B） |
| Empty 生境 IDE polish | 空生境 IDE 深打磨、始祖预选 | → **0.5.3** unless blocking introduce |
| Capability hub assist | skill/capability 中枢撰写 | Later-D |
| Session engine v2 | Multimodal day-1 protocol | `.omo/drafts/session-engine-v2.md`（原 v4+ **后移**） |
| Gene LLM real | Richer distill than heuristics | Former P16c |
| Voice / channels / multi-runtime / multi-compute / DLP / OTel / backup / S3 | nodeskclaw parity candidates | Former P16e–m |

Priority among remaining 3.5.x slices is **re-decided from orbstack human QA**, not copied blindly from the archived P16 queue.

---

## 6. Hard process rules

### 6.1 Deploy to orbstack after every implementation wave (mandatory)

**Standing user rule (2026-07-28, reaffirmed 2026-07-29):** after development for a wave (or any bugfix that changes runtime behavior) completes:

1. Commit on the feature branch → merge to `main` (fast-forward when possible).
2. Run `bash scripts/deploy-to-orbstack.sh` (idempotent).
3. Verify pods Ready; smoke via curl + browser on the live cluster.
4. Leave the `eyot` namespace running for human inspection.
5. Record evidence under `.omo/evidence/` when material.

**Forbidden**: ship "code done" without orbstack update; fix live DB with ad-hoc SQL; delete namespace `eyot`.

Full ops: AGENTS.md "Eyot Deployment Operations Rules" + "Persistent Fix Policy"; `.omo/evidence/orbstack-operations.md`.

### 6.2 Other non-negotiables (summary)

- Soft delete only; Partial Unique Indexes for uniqueness.
- Alembic autogenerate for schema; never hand-written fake revision IDs.
- No emoji in product/UI/docs/commits without explicit user permission; icons via `lucide-react`.
- i18n for user-visible strings (`zh-CN` / `en`).
- pytest never touches shared `eyot_dev` on `local-pgvector`.
- Persistent Fix Policy: fixes are code → commit → image → rollout — not monkey-patches.

### 6.3 Branch workflow

`main` is source of truth. Each wave: `git checkout main && git checkout -b feat/<kebab>`. Merge back after acceptance + orbstack deploy.

---

## 7. Long-term directions (not active waves)

Recorded so future planners do not lose intent:

1. **Session engine v2** — lighter store; multimodal `{text|image|audio|video}` first-class; Tunnel-class transport. Draft: `.omo/drafts/session-engine-v2.md`.
2. **nodeskclaw surface parity (selective)** — Tunnel, Voice, Knowledge scopes, multi-runtime, multi-compute, Feishu, etc. Only after PRD-v2 control plane is solid.
3. **Plan hygiene** — phase plans immutable after merge; drift goes to evidence, not silent plan rewrites.

---

## 8. Document map

### Canonical (`docs/`)

| File | Purpose |
|---|---|
| **`roadmap.md`** | **This file — system blueprint + living roadmap** |
| `prd-v1.md` | PRD generation 1 (MVP UX); historical + residual reference |
| `prd-v2.md` | PRD generation 2 — **archived**（`docs/archive/prd-v2.md`；设计以 `audit-product-design.md` 为准） |
| `terminology.md` / `metaphor-name-table.md` | Naming（**v5 命名基线**：大陆/区域/生境/始祖/血脉/后裔/5 动物/术语新词；15d 版归档于 `docs/archive/terminology-15d.md` + `docs/archive/metaphor-name-table-15d.md`）|
| `domain-model.md` / `api-architecture.md` / `*-system.md` / `observability.md` / `product-positioning.md` | Subsystem contracts (refresh when code lands) |

### Planning (`.omo/`)

| Path | Purpose |
|---|---|
| `plans/INDEX.md` | Active executable plans index |
| `plans/phase-15f-prd-v1-implementation.md` | Last completed impl plan (PRD-v1) |
| `plans/prd-v2-generation.md` | PRD-v2 writing plan (doc-only; complete) |
| `plans/archive/` | All finished phase plans + **archived roadmaps** |
| `drafts/` | In-flight design (15d locks, session-engine-v2, …) |
| `evidence/` | Capability maps, gap, drift, deploy, orbstack ops |

### External references

| Project | Path | Layer |
|---|---|---|
| nodeskclaw | `/Users/xuwenrui/Documents/Codes/Researches/nodeskclaw/` | product ancestor |
| oh-my-openagent (senpi / oh-my-pi surface) | `/Users/xuwenrui/Documents/Codes/github/oh-my-openagent/` (pin tags) | **Workspace** peer |
| pi (`@mariozechner/pi-coding-agent`) | upstream pi coding agent | **Instance / 化身** driver |
| jcode | https://github.com/1jehuang/jcode | **Collab / delivery semantics** reference for v4.7（soft interrupt、handoff、file-touch；非 Workspace 产品对标、非 Instance driver） |

---

## 9. Decision log (roadmap-level)

| Date | Decision |
|---|---|
| 2026-07-28 | P15 renamed foundation wave; multi-tenant deferred out of P15; Persistent Fix + orbstack rules locked in AGENTS.md |
| 2026-07-28 | P15d naming + 36 decisions approved; `docs/` becomes product SoT |
| 2026-07-29 | PRD-v1 implemented (P15f); PRD-v2 written (multi-tenant + agent stack) |
| 2026-07-29 | **Roadmap canonicalized to `docs/roadmap.md`**; archive `.omo/plans/eyot-v2-roadmap.md` + `phase-15-foundation-roadmap.md`; next engineering wave = PRD-v2 implementation after Plan-mode plan |
| 2026-07-29 | Reaffirm: every completed development wave deploys to orbstack for human test |
| 2026-07-29 | PRD-v2 修订：Namespace = **场景分区**（非 env）；Vault = DB KV（MinIO/S3 远期）；ER 补全 **CerebellumAgent 中央智能体 1:1** |
| 2026-07-29 | **PRD-v2 implementation Done** — hard-cut tenant/genes/portal; plan at `.omo/plans/prd-v2-implementation.md` |

| 2026-07-30 | **PRD-v3 written** — Provider defaults, implicit system hub, promote update/fork（回魂/派生）+ transmute UX; `AGENTS.md` Rule 5 orbstack-only |
| 2026-07-30 | **Runtime spine lock** — Workspace ≈ more flexible/observable senpi·oh-my-openagent·oh-my-pi; each 化身 driven by **pi** (sandboxed preferred; React optional). Reject equating pi with Senpi CLI |
| 2026-07-31 | **Version track lock** — **3.5.x** = main-flow product closed loop (iterative fixes OK); **3.6** = whole UI major refactor. Plan: `.omo/plans/product-version-track-3-5-3-6.md` |
| 2026-08-01 | **Design correction → v4** — `audit-product-design.md` SoT；实现切片 `v4-0`…`v4-9` |
| 2026-08-02 | **附录 B 决议** — OrganizationContract + 原子 UserGene/基因组；Org 选择页；成员赋基因；Knowledge override；clone can_*。见 `audit-v4-design-review.md` |

| 2026-08-02 | **V47-1…11 签核** — 全部接受顾问建议；v4.7 可排队实现（仍依赖 v4.5/v4.6）。 |

| 2026-08-07 | **v5 完整世代立项** — 四切片（v5.0 命名 / v5.1 定义 / v5.2 UIUX / v5.3 视觉）；MAJOR bump 5.x；grill-me 会话闭环全部待定项：5 常驻始祖（狐狸/海狸/麻雀/郊狼/狮子）+ 6 subagent 能力（唤灵/灵视/衡判/游魂/潜知/百瞳 退出体系）、三层名始祖/血脉/后裔、结构术语大陆/区域/生境/迁徙路线、其余术语全量新词（成员/信号塔/标本/粮仓/足迹/诞生记录/领地地图/蜕变/演化/领悟/兽道）、rank 全量退役、slug 直接改名+存量 UPDATE、代码名不动。SoT `.omo/evidence/v5-rename-decisions.md` + `.omo/plans/0x-roadmap.md`；v4.9.5 closeout 先行。 |
| 2026-08-09 | **v5.0 命名波交付 + v5.1 定义波执行中** — 版本 5.0.2；6 降级 Memory 物理删光（迁移 `78137b7985e5` M2）；T1 落地 6 能力 subagent agent .md（intent/architecture/quality/explore/research/vision）；T6 Tunnel 协议清理（提交 a3f0b85：错误码中性化 host_spawn_error/host_stdin_closed/turn_rejected/host_error + done payload 去 finish_reason + control interrupt）。SoT 同步：`v5-rename-decisions.md` §六.2「Memory 经验回流」条目作废 + §七.1 扩充；terminology / metaphor-name-table 补能力 id 列。 |

*Next update trigger: a v4 slice closes, or implementation of a signed plan starts.*
