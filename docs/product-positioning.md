> **Pre-v4 reference**: Conflict with `.omo/evidence/audit-product-design.md` → audit wins. Awaiting v4 PRD rewrite.
>

# Cocoa: Product Positioning

> **Code rename pending (15d-rename wave)**: This doc describes target architecture (15d+). Current code uses old naming.

A persistent studio where human operators and AI entities collaborate on long-running work.

## What Cocoa is

Cocoa gives you a workspace. You step into it as a director, and your AI entities, each with their own BaseClass identity, persistent memory, and isolated workspace, are already there. You plan, delegate, review, and iterate. They work, report back, and remember what they learn. The workspace stays open across sessions, across failures, across compaction events.

Under the hood, Cocoa is a K8s-native multi-agent control system. Every AI entity is a template (BaseClass) that can be materialized into multiple isolated instances in different workspaces. Messaging is near-neighbor only, with explicit collaboration rings (passages) that replace the flat broadcast-fanout that pollutes context in prototype systems. The portal is the visual surface: a debug-first, operator-facing UI that lets you see what each entity is doing, read their logs, and route commands.

## Who it is for

Cocoa is built for operators who manage teams of AI entities running multi-step, long-lived knowledge work. The primary user is a human director who plans, delegates, reviews, and course-corrects, supported by a roster of AI entities with defined roles (planner, worker, oracle, explorer, reviewer). The system assumes you need persistent state, cross-instance memory, and a visual control surface, not a one-shot CLI prompt.

## Structural defects Cocoa fixes

Cocoa inherits the product logic of nodeskclaw, a prototype multi-agent workspace, and addresses three known structural defects from that prototype:

- **Near-neighbor messaging with explicit passages (D3).** The prototype used a flat 30-message log for context assembly, with no per-conversation filtering and a disabled topology check. Cocoa replaces this with near-neighbor-only messaging: nodes talk only to adjacent neighbors defined by their passage (Corridor). Collaboration happens through explicit rings, bounded mini-group-chats that keep context scoped and prevent the pollution that made the prototype's message bus unusable at scale.

- **Entity = BaseClass/template with N isolated instances (D1).** The prototype coupled one entity identity to one running instance. If you needed two copies of the same reviewer in two different projects, you could not do it. Cocoa separates the entity (a persistent role identity: BaseClass manifest plus shared memory) from the instance (a materialization in one workspace, with its own isolated workspace). One BaseClass spawns many instances, each in its own workspace, each with its own PVC.

- **BaseClass system replacing engine selection (D5).** The prototype forced operators to choose a model engine (OpenCLaw, Hermes) at entity creation time. Cocoa replaces this with a BaseClass system: you choose an AI persona (Planner, Worker, Oracle, Explorer, Reviewer) defined by a manifest of skills, tools, model, and prompt. The BaseClass is the interface; the engine is an implementation detail. This is the difference between picking a car engine and picking a driver.

## Runtime spine (locked 2026-07-30)

Two layers — never conflate:

| Layer | Peer / driver | Cocoa |
|-------|---------------|-------|
| **Workspace** | senpi · oh-my-openagent · oh-my-pi | Cocoa Workspace = a more flexible, more observable evolution of that surface (portal + harness + topology + multi-human) |
| **化身 (Instance)** | **pi** sandboxed agent runtime (React optional, less preferred) | Each Instance pod is driven by pi. Entity overlay → AgentConfig → pi |

**Incorrect (do not write):** "Cocoa's agent runtime is pi (Senpi CLI)". Senpi is a harness/adapter over Pi — Workspace-layer peer, not the per-Instance driver.

## What Cocoa adds beyond oh-my-openagent / senpi

oh-my-openagent (and its senpi / oh-my-pi surfaces) provide the loop-engineering harness (boulder state, plan continuation, notepad, evidence ledger, compaction survival) that Cocoa ports into the **Workspace** layer. Per-化身 execution is **pi**, not Senpi CLI. Cocoa adds four things that make it a different product:

- **Visual portal, not a CLI surface.** oh-my-openagent / senpi run as harness surfaces inside a coding-agent CLI session. Cocoa wraps the same class of harness in a web-based operator portal with per-entity command autocomplete, log panels, and topology visualization. You see your workspace, not a terminal scrollback.

- **Multi-human participation.** Those peers are single-operator. Cocoa supports multiple humans and multiple AI entities co-managing the same workspace. A human director approves and forwards; another human reviews; AI entities pass work along. All share the same blackboard, memory, and vault through permission-gated access.

- **Persistent, cross-instance shared memory.** Their notepad is per-session. Cocoa's memory is per-entity and survives across instances, sessions, and compaction. Each entity accumulates experience as append-only memory entries. A `/distill` command consolidates memory into a learnable skill added to the entity's BaseClass, closing the loop from experience to capability.

- **Skill-creating and the orchestration harness as differentiator.** The loop-engineering harness itself, ported and extended at the Workspace layer, is Cocoa's core differentiator. Boulder state tracks long-running work across sessions. Plan continuation resumes interrupted plans. The evidence ledger records decisions and their rationale. The notepad captures learnings, issues, and problems. This is not a thin wrapper over an LLM API; it is a self-closing orchestration system that learns from its own execution.

## Reference comparison

| System | Scope | Operator | Messaging | Memory | Visual | Instance driver |
|--------|-------|----------|-----------|--------|--------|-----------------|
| **nodeskclaw** | Multi-agent workspace (prototype) | Single human | Flat broadcast, polluted context | None | Web UI (basic) | engine pick at create |
| **oh-my-openagent / senpi** | Agent BaseClasses + loop harness (CLI) | Single human (CLI) | None (no multi-agent studio) | Per-session notepad | None | harness over Pi / other |
| **Cocoa** | Multi-agent control studio | Multiple humans + AI team | Near-neighbor + passages, scoped | Per-entity, persistent, cross-instance | Web portal, debug-first | **pi** per 化身 |

## Who should adopt Cocoa

If you are running AI agents that need to collaborate across days, remember what they learned, and stay visible to a team of human operators, Cocoa is the control surface for that work.

## Presets → BaseClasses

Cocoa ships with **11 BaseClasses** (referred to as "presets" in legacy code): Planner, Worker, Oracle, Explorer, Reviewer, plus 6 additional roles covering the full multi-agent collaboration spectrum. Each BaseClass defines a manifest of skills, tools, model, and prompt — the preset system from nodeskclaw has been reified into first-class BaseClasses with isolated memory, instance spawning, and `/distill` self-improvement.
