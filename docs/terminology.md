> **Pre-v4 reference**: Conflict with `.omo/evidence/audit-product-design.md` → audit wins. Awaiting v4 PRD rewrite.
>

# Cocoa Terminology Glossary (15d)

> **Canonical source**: Naming decisions locked in `.omo/drafts/phase-15d-naming-system.md`. All 36 decisions (N1-N10, D1-D6, B1-B6, U1-U8, DOC1-DOC5) are approved.
> **Code rename pending**: This doc describes the target architecture (15d+). The current codebase (P0-P15b) still uses old naming; a dedicated rename wave (15d-rename) is deferred until after P16d Org model decision.

One-line definitions for every Cocoa code-term (backend), display-name (frontend Cthulhu-themed), and protocol entity. Derived from the naming system and the core domain model. Code-terms stay English; display-names in parentheses are for product UI reference.

---

## Structure Terms (3-Layer Tenant + 3-Tier Entity)

### Tenant Hierarchy

- **Organization** (世界) — Top-level isolation unit. **PRD-v2 first-class**; single-tenant default slug=`default`.
- **Namespace** (次元) — Within an Organization: **scenario partition** (e.g. coding vs social-media), **not** env (dev/staging/prod). **PRD-v2 first-class**; Entity belongs here so scenario identity spans multiple Workspaces.
- **Workspace** (空间) — Within a Namespace: a concrete workstream (e.g. a product system or a publish platform). Current code may still say `Office` until rename wave. Single-tenant default: one Workspace shared by all users. Starts empty (no auto-preloaded Entities).

### Entity Hierarchy (the "agent stack")

- **BaseClass** (神职) — Preset template defining rules, prompt, commands, tools, and provider config. Created by humans or distilled from Entity experience. System-scoped. 11 built-in BaseClasses defined in §4 of the naming system.
- **Instance** — Running materialization of an Entity in one Workspace. One Instance per pod. Lifecycle ≤ Workspace. **Invariant (PRD-v3.4)**: at most one active Instance per `(workspace_id, entity_id)` because `@slug` addresses the Entity. **Product display is scene-dependent (not「旧称→新称」)**:
  - **眷族视角**（眷族详情、晋升/批量重启、次元「化身」只读聚合）：叫 **化身** — 相对眷族的运行体。
  - **空间层与真人并列**（空间卡计数、空间 tab、拓扑座位）：叫 **迷失者**，对位 **觉醒者**。
  - Do **not** force-rename 眷族侧「化身」为迷失者；do **not** call workspace human seats 契印.
- **Entity** (眷族) — Instantiation of a BaseClass **per-Namespace**, with identity + accumulated Memory. Scenario-scoped so one Entity can spawn Instances across Workspaces in that Namespace. Can be promoted/transmuted via distillation actions.

### Structural Concepts

- **Membership** — Workspace presence with posx/posy + role. Exclusive-FK: user XOR instance. **PRD-v3.4 product names**: user row = **觉醒者** (director present in workspace); instance row = topology seat for **迷失者**. Not called 契印.
- **NamespaceContract** (契印) — **PRD-v3.4**. Namespace ↔ User seal. The **only** product use of the name 契印. Auto-ensured when a user creates/joins a workspace in that namespace.
- **Passage** (通道) — Adjacency edge between two Memberships, defining the selectable neighbor set for messaging. CorridorNode dropped.
- **CentralHub** (主脑) — Per-Workspace 协作中枢容器，含 4 脑区（穹窿 / 额叶 / 脑干 / **小脑=内置中央智能体 CerebellumAgent 1:1**）。Display 中文"主脑"，backend 代码名 `CentralHub`。
- **CerebellumAgent** (小脑 / 中央智能体) — Built-in system agent on every CentralHub. Auto-created; not soft-deletable; not shown on topology. See `docs/blackboard-system.md` §4 and PRD-v2 §8.2.1.
- **Vault** (冰封库) — Cold archive per Workspace. PRD-v2: DB KV (`vault_entries`, optional inline value); eventual MinIO/S3 via `archived_key` — not expanded in v2.
- **Memory** (记忆沉淀) — Append-only per-Entity memory log, indexed by kind (experience/lesson/decision/problem) and time. No `updated_at` column. Accumulates across Instances.

### Runtime Concepts

- **Workspace control plane** — Cocoa's operator + harness surface (Portal, Supervisor, Boulder, Passage, CentralHub, deploy, observability). Product peer: a more flexible / observable **senpi · oh-my-openagent · oh-my-pi**. Not the per-Instance agent binary.
- **pi runtime** — Preferred sandboxed agent loop that drives each **Instance / 化身**. Entity `system_prompt` + `config_override` serialize to pi AgentConfig. React runtime is an optional alternative (less preferred for sandbox stability). **Not** Senpi CLI.
- **LoopState** (心智状态) — Harness runtime state for an Instance: loop_status (6 states), continuation_count, breaker_config, last_checkpoint_at.
- **DeployRecord** (降世记录) — K8s deployment lifecycle record: 9-step pipeline from build to pod-ready.
- **InstanceProviderConfig** — LLM provider configuration for an Instance (openai-compatible, anthropic, etc.). Internal config, no UI equivalent.
- **Topology** (心灵图景) — Spatial visualization of Workspace members as SVG nodes with glow halos, 3 interaction modes (Select/Connect/Move), and message-flow particle animation.
- **delivery_mode** (投递模式, v4.7) — How a collaboration/inject payload reaches an Instance: `notify` (event only, no auto-wake), `soft_inject` (safe-point insert into running loop), `wake` (start/resume turn if idle). Normative in `.omo/plans/v4-7-harness-collab.md` / `audit-product-design.md` §九. Pattern study: [jcode](https://github.com/1jehuang/jcode) soft interrupt — not a Cocoa product synonym for swarm chat.

---

## BaseClasses (11 Built-in 神职)

Per naming system §4. Slug = kebab-case identifier (DB layer). Display = i18n key (UI layer). DB does not store display_name column.

| # | Slug | Display | Role | omo Agent Source |
|---|---|---|---|---|
| 1 | `mi-shi` | 密士 | Interview planner, plan mode sticky, `.omo` plan writer | Prometheus (Strategic Planner) |
| 2 | `huan-ling` | 唤灵 | Intent analysis, pre-planner before Prometheus | Metis (Pre-planning Consultant) |
| 3 | `an-xing` | 暗行 | Solo full-stack coder, boulder-pusher | Sisyphus (Main Coder) |
| 4 | `an-ying` | 暗影 | Junior coder, cheap/fast | Sisyphus-Junior |
| 5 | `zhu-jin` | 铸金 | Autonomous deep worker, goal-driven | Hephaestus |
| 6 | `ling-shi` | 灵视 | Read-only architecture / hard debugging | Oracle (High-IQ Reasoning) |
| 7 | `heng-pan` | 衡判 | Quality gate: review/approve/reject | Momus (Critic) |
| 8 | `you-hun` | 游魂 | Codebase grep / exploration | Explore |
| 9 | `qian-zhi` | 潜知 | External reference + multi-repo + docs | Librarian |
| 10 | `bai-tong` | 百瞳 | Visual / media / audio analysis | Multimodal-Looker |
| 11 | `jiu-ri` | 旧日 | Top-level delegation / monitoring / approval | Atlas (Orchestrator) |

---

## Lab Ranks (克苏鲁神秘系)

Progression from shallow perception → deep knowledge → awakened mastery.

- **Intern** (浅识者) — Stateless hot-load rank: no persistent session, no memory read, fresh invocation each time. Barely glimpsed the cosmic truth.
- **Researcher** (深潜者) — Full BaseClass plus memory rank: persistent, accumulates experience across invocations. Diving ever deeper into the mysteries.
- **Director** (觉醒者) — Human operator rank: highest authority, approval and forwarding rights. Fully awakened to direct others. Not a BaseClass; human users hold this.

---

## Sub-entities (Data Layer)

Code-term-only entities from the core domain model. No product UI display-names.

- **User** — Human authentication identity: username, email, password hash; the login entity.
- **BaseClass** (was EmployeePreset) — Persisted preset record storing slug, manifest JSONB, and version.
- **Entity** (was Employee) — Per-Namespace identity referencing a BaseClass, with accumulated memory across Workspaces in that scenario.
- **Membership** (觉醒者 / 迷失者拓扑位；勿称契印) — Workspace presence seal. See Structural Concepts.
- **NamespaceContract** (契印) — Namespace-scoped human contract (PRD-v3.4).
- **BlackboardFile** / **FornixFile** — File record on CentralHub fornix, with storage key, content type, and directory tree metadata.
- **CerebellumAgent** — Built-in central agent (1:1 CentralHub); system-owned, not a Membership.
- **VaultEntry** — Archived KV entry in a Vault (`value` inline in v2; `archived_key` for future object store).
- **Memory** (was MemoryEntry) — Append-only memory log entry per Entity, indexed by kind and time.

---

## Concepts

- **Entity-as-role-identity** — Entity is a persistent role identity composed of a BaseClass manifest plus shared cross-instance Memory; it grows as memory accumulates.
- **Instance=materialization** — An Instance is a concrete materialization of an Entity in one Workspace, with isolated workspace and runtime.
- **near-neighbor messaging** — Messaging restricted to passage-defined adjacent nodes only; no broadcast fan-out, unlike flat log-based group chat.
- **passage** — The editable neighbor set of a node; defines the selectable recipient list for directed messaging within a Workspace.
- **activation trigger** — Event that causes a node to sync topology and state: daily-report self-sync, on-mention, or scheduled task invocation.
- **promotion (晋升)** — Instance → Entity: capture Instance runtime state + Memory back into the Entity. In-place enhancement.
- **transmutation (炼化)** — Entity → BaseClass: distill accumulated Entity Memory into a new reusable BaseClass. Creates a new slug, available across Workspaces.
- **slash-protocol** — Structured turn-based command grammar: a Turn is a list of Directives, each with optional target, command, args, and content-ref.
- **directive** — A single command unit within a Turn: target_entity, cmd, args, content_ref, and raw_text.
- **command-registry** — Registry of four command families: GLOBAL (/read, /list, /write, /archive), PER-PRESET (defined in manifest.commands), CONTROL (/interrupt, /pause, /resume, /status, /snapshot), LEARNING (/distill, /consolidate, /reflect). Priority-ordered in directive_router.py::route_turn().
- **content-ref** — A scope-qualified reference to content: mandatory scope prefix (workspace|blackboard|vault|memory) with optional path.
- **composer compartmentalization** — The Composer UI splits a message into per-entity compartments before send; the user sees and confirms what each entity receives, emitted as a structured Turn.

---

*Derived from `.omo/drafts/phase-15d-naming-system.md` (2026-07-28). Code rename pending 15d-rename wave (after P16d Org model decision).*
