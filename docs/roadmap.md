# Cocoa System Roadmap & Blueprint

> **Status**: Living document. Canonical project roadmap + system goal blueprint.
> **Authority**: Supersedes `.omo/plans/archive/cocoa-v2-roadmap.md` and `.omo/plans/archive/phase-15-foundation-roadmap.md` (archived 2026-07-29).
> **Product specs**: `docs/prd-v1.md` · `docs/prd-v2.md` · `docs/prd-v3.md` · **`docs/prd-v3.4.md` (active)** · Later/v4+ deferred.
> **Naming**: `docs/terminology.md` + `docs/metaphor-name-table.md` (15d locked).
> **Last revision**: 2026-07-30.

---

## 0. How to use this doc

| Reader | Read first | Then |
|---|---|---|
| Planner / new session | §1 blueprint + §2 iteration model + §5 wave status | PRD of the active wave; capability maps under `.omo/evidence/` |
| Worker implementing a wave | Active PRD + this §5 "Next" row + §6 hard rules | Phase plan under `.omo/plans/` (when written) |
| Reviewer | §3 current state vs §4 target | Diff against PRD appendix C |

**Do not** treat archived `.omo/plans/archive/*roadmap*` as current direction.

---

## 1. System goal blueprint

### 1.1 One-sentence product

**Cocoa is a K8s-native multi-agent control studio**: human directors summon reusable AI role templates (神职 / BaseClass), specialize them into scenario identities (眷族 / Entity), materialize running pods (化身 / Instance), observe them on a topology canvas, and distill runtime experience back into reusable capability and new roles.

### 1.2 Why it exists

Traditional chat agents reset every session. Cocoa closes three loops that chat tools leave open:

| Loop | Without Cocoa | With Cocoa |
|---|---|---|
| **Identity** | Disposable reply | BaseClass → Entity → Instance (L1 / L2 / L3 progressive specialization) |
| **Memory** | Context window only | Append-only Memory per Entity + promote / transmute |
| **Collaboration** | 1:1 flat chat | Shared Workspace + Passage near-neighbor messaging + CentralHub + visual Topology |

Inherited from `nodeskclaw`, rebuilt lighter and vision-first. Loop engineering (Boulder / circuit breakers / notepad) is borrowed from `oh-my-openagent` (pin tags; do not trust its unstable `dev` tree) — that family (senpi / oh-my-openagent / oh-my-pi) is the **Workspace-layer** peer Cocoa aims to surpass in flexibility and observability. Each **化身 (Instance)** is driven by a sandboxed **pi** agent runtime (React runtime optional, less preferred) — never by Senpi CLI as the Instance driver.

### 1.3 What Cocoa is / is not

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

| Layer | Peer / driver | Cocoa role |
|---|---|---|
| **Workspace control plane** | senpi · oh-my-openagent · oh-my-pi (Cocoa = more flexible + more observable evolution) | Portal + Harness Supervisor + Passage + CentralHub + deploy + observability |
| **Instance agent runtime** | **pi** (sandboxed; preferred). React runtime optional | Each 化身 pod runs under pi; Entity overlay → AgentConfig → pi |

| Layer | Mechanism | Status vs PRD-v2 |
|---|---|---|
| Harness | Supervisor + 4 breakers + control commands | Done (P8); keep (Workspace layer) |
| Instance driver | **pi via Host RPC + Tunnel WS** | Done (PRD-v3.5): `cocoa-instance-host` + `WS /api/v1/tunnel/connect`; stub fallback when offline |
| Deploy | 9-step K8s pipeline + DeployRecord + SSE | Done (P11–P15a); keep |
| LLM | 4 providers + ModelCatalog + LLMDistiller | Done (P14a); keep |
| Messaging | Passage-gated near-neighbor + 4 command families | Done (P5/P8/P10); rename Corridor→Passage pending |
| CentralHub | 4 brain regions (Fornix + 3 new in P15f) | Partial → complete under v2 polish |
| Learning | reap / promote / transmute / compose endpoints | P15f scaffold; align to PRD-v2 two-chain rules |
| Multitenancy | Org / Namespace tables + Entity.namespace_id | **PRD-v2 implementation wave** |
| Genes | user_genes + ai_genes unified schema | **PRD-v2 implementation wave** |

---

## 2. Iteration model — PRD-driven

Cocoa no longer plans primarily as open-ended "P-N feature waves". After foundation (P0–P15b) and naming lock (P15d), **product truth lives in PRD documents under `docs/`**, and engineering waves implement a named PRD slice.

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Lock naming / ontology     (P15d — done)                 │
│ 2. Write PRD (interaction + data decisions)                 │
│ 3. Write /approve execution plan (.omo/plans/)              │
│ 4. Implement on feature branch from master                  │
│ 5. Tests + evidence                                         │
│ 6. Merge master                                             │
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

**PRD generations**:

| PRD | Intent | Engineering wave | Status |
|---|---|---|---|
| **v1** | Single-tenant MVP UX + distillation UI + 3-layer market scaffold | P15e (doc) → **P15f (impl)** | Doc done; backend+portal must-haves landed on master |
| **v2** | Multi-tenant hierarchy + agent stack redesign + gene dual tables + IDE UX | **Done** (2026-07-29) — `.omo/plans/prd-v2-implementation.md` | Hard-cut schema + APIs + portal; orbstack redeploy for human QA |
| **v3+** | Session-engine multimodal, Tunnel, Voice, … | Far queue (§7) | Draft only |

Code identifiers follow 15d/v2 names (`Workspace`, `Entity`, `Passage`, `BaseClass`). Pre-v2 names remain only in alembic history.

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

Orbstack namespace `cocoa` is the **persistent human inspection environment**. See `.omo/evidence/orbstack-operations.md` + `.omo/evidence/cocoa-deployment-state.md`. Every implementation wave that changes backend/portal/deploy **must** end with `scripts/deploy-to-orbstack.sh` (§6).

---

## 4. Target architecture (PRD-v2 condensed)

Authoritative detail: `docs/prd-v2.md`. This section is the blueprint digest only.

### 4.1 Data

- **18 core tables** + **2 N:N** (`user_user_genes`, `base_class_ai_genes`) + conceptual System / Knowledge / CapabilityMarket (+ Event audit table outside the 18).
- Soft delete everywhere; Partial Unique Indexes only.
- Membership exclusive-FK (user XOR instance); Passage M↔M only.
- Memory append-only (no `updated_at`).

### 4.2 Runtime compatibility

Entity overlays serialize toward **pi AgentConfig** (schema family shared with oh-my-openagent `AgentOverrideConfigSchema` overlay; pin `oh-my-openagent` tag, e.g. v4.19.2, for overlay field names only). The **Workspace** control plane (Harness / Boulder / Portal) is Cocoa's evolution of senpi · oh-my-openagent · oh-my-pi. Each **Instance** is driven by **pi**, not by Senpi CLI. Boulder remains the control-plane engine; workflow-gene is rejected — orchestration stays in Harness.

### 4.3 Default deployment shape

```
orbstack K8s
  namespace cocoa
    cocoa-backend  : API + harness + deploy controller
    cocoa-portal   : React operator UI
    cocoa-postgres : tenant DB for the live env
```

Local pytest continues to use `cocoa_test_*` clones on `local-pgvector` — never `cocoa_dev` on that shared instance.

---

## 5. Wave status & queue

### 5.1 Completed (archive only)

Full history: `.omo/plans/archive/` + `.omo/plans/archive/cocoa-v2-roadmap.md` (pre-PRD era status table) + `.omo/plans/archive/phase-15-foundation-roadmap.md` (P15 foundation notes).

| Milestone | Outcome |
|---|---|
| P0–P14a | Core studio + K8s + LLM |
| P15a–b | Orbstack + onboarding foundation |
| P15d | Naming + product ontology lock |
| P15e | PRD-v1 written |
| P15f | PRD-v1 must-have implementation |
| PRD-v2 generation | `docs/prd-v2.md` decision-complete |
| **PRD-v2 impl** | Hard-cut tenant schema + genes + two-chain learning + portal IDE — `.omo/plans/prd-v2-implementation.md` |

### 5.2 Next (immediate)

| Slot | Title | Spec | Plan | Notes |
|---|---|---|---|---|
| **PRD-v3.5** | Tunnel + pi Host 真连接 | `.omo/plans/prd-v3-5-tunnel-pi.md` | `feat/prd-v3-5-tunnel-pi` | Product **3.5.0** |
| **PRD-v3.4.1** | Composer `@`/`/` 协议 + 流式终态 + deploy-existing + 拓扑 fit | `docs/prd-v3.4.1.md` | feat/prd-v3-4-contracts-introduce | Product **3.4.1** (verified) |

PRD-v3.5 复活 P14b：Instance Host 出站 Tunnel + `pi --mode rpc`；Composer 复用现有 SSE。

### 5.3 Near backlog (after PRD-v3.5)

| Slot | Theme | Source |
|---|---|---|
| **PRD-v3.4.2** | 全神职基础 gene + capability（空间会话 / 拓扑邻接说话） | 建在 3.5 tunnel/pi 上 |
| Avatar presets UI | 用户/眷族预设头像切换 | PRD-v3 Later-A（**后移**） |
| Visual + 神职图 | 主视觉换皮、候选图挂卡片 | Later-B（**后移**） |
| Empty IDE polish | 空空间 IDE 深打磨、神职预选 | Later-C（**后移**） |
| Capability hub assist | skill/capability 中枢撰写 | Later-D（**后移**） |
| Polish | Empty states, error UX, audit filters, i18n sticky | Former P15c leftovers |
| Session engine v2 | Multimodal day-1 protocol | `.omo/drafts/session-engine-v2.md`（原 v4+ **后移**） |
| Gene LLM real | Richer distill than heuristics | Former P16c |
| Voice / channels / multi-runtime / multi-compute / DLP / OTel / backup / S3 | nodeskclaw parity candidates | Former P16e–m |

Priority among near-backlog items is **re-decided after PRD-v3.5 human QA on orbstack**, not copied blindly from the archived P16 queue.

---

## 6. Hard process rules

### 6.1 Deploy to orbstack after every implementation wave (mandatory)

**Standing user rule (2026-07-28, reaffirmed 2026-07-29):** after development for a wave (or any bugfix that changes runtime behavior) completes:

1. Commit on the feature branch → merge to `master` (fast-forward when possible).
2. Run `bash scripts/deploy-to-orbstack.sh` (idempotent).
3. Verify pods Ready; smoke via curl + browser on the live cluster.
4. Leave the `cocoa` namespace running for human inspection.
5. Record evidence under `.omo/evidence/` when material.

**Forbidden**: ship "code done" without orbstack update; fix live DB with ad-hoc SQL; delete namespace `cocoa`.

Full ops: AGENTS.md "Cocoa Deployment Operations Rules" + "Persistent Fix Policy"; `.omo/evidence/orbstack-operations.md`.

### 6.2 Other non-negotiables (summary)

- Soft delete only; Partial Unique Indexes for uniqueness.
- Alembic autogenerate for schema; never hand-written fake revision IDs.
- No emoji in product/UI/docs/commits without explicit user permission; icons via `lucide-react`.
- i18n for user-visible strings (`zh-CN` / `en`).
- pytest never touches shared `cocoa_dev` on `local-pgvector`.
- Persistent Fix Policy: fixes are code → commit → image → rollout — not monkey-patches.

### 6.3 Branch workflow

`master` is source of truth. Each wave: `git checkout master && git checkout -b feat/<kebab>`. Merge back after acceptance + orbstack deploy.

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
| `prd-v2.md` | PRD generation 2 — **active product target** |
| `terminology.md` / `metaphor-name-table.md` | Naming |
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

---

## 9. Decision log (roadmap-level)

| Date | Decision |
|---|---|
| 2026-07-28 | P15 renamed foundation wave; multi-tenant deferred out of P15; Persistent Fix + orbstack rules locked in AGENTS.md |
| 2026-07-28 | P15d naming + 36 decisions approved; `docs/` becomes product SoT |
| 2026-07-29 | PRD-v1 implemented (P15f); PRD-v2 written (multi-tenant + agent stack) |
| 2026-07-29 | **Roadmap canonicalized to `docs/roadmap.md`**; archive `.omo/plans/cocoa-v2-roadmap.md` + `phase-15-foundation-roadmap.md`; next engineering wave = PRD-v2 implementation after Plan-mode plan |
| 2026-07-29 | Reaffirm: every completed development wave deploys to orbstack for human test |
| 2026-07-29 | PRD-v2 修订：Namespace = **场景分区**（非 env）；Vault = DB KV（MinIO/S3 远期）；ER 补全 **CerebellumAgent 中央智能体 1:1** |
| 2026-07-29 | **PRD-v2 implementation Done** — hard-cut tenant/genes/portal; plan at `.omo/plans/prd-v2-implementation.md` |

| 2026-07-30 | **PRD-v3 written** — Provider defaults, implicit system hub, promote update/fork（回魂/派生）+ transmute UX; `AGENTS.md` Rule 5 orbstack-only |
| 2026-07-30 | **Runtime spine lock** — Workspace ≈ more flexible/observable senpi·oh-my-openagent·oh-my-pi; each 化身 driven by **pi** (sandboxed preferred; React optional). Reject equating pi with Senpi CLI |

*Next update trigger: PRD-v3 implementation plan approved, or v3 wave merged + orbstack verified.*
