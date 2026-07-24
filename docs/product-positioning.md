# Cocoa: Product Positioning

A persistent studio where human operators and AI employees collaborate on long-running work.

## What Cocoa is

Cocoa gives you an office. You step into it as a director, and your AI employees, each with their own preset identity, persistent memory, and isolated workspace, are already there. You plan, delegate, review, and iterate. They work, report back, and remember what they learn. The office stays open across sessions, across failures, across compaction events.

Under the hood, Cocoa is a K8s-native multi-agent control system. Every AI employee is a template (preset) that can be materialized into multiple isolated instances in different offices. Messaging is near-neighbor only, with explicit collaboration rings that replace the flat broadcast-fanout that pollutes context in prototype systems. The portal is the visual surface: a debug-first, operator-facing UI that lets you see what each employee is doing, read their logs, and route commands.

## Who it is for

Cocoa is built for operators who manage teams of AI employees running multi-step, long-lived knowledge work. The primary user is a human director who plans, delegates, reviews, and course-corrects, supported by a roster of AI employees with defined roles (planner, worker, oracle, explorer, reviewer). The system assumes you need persistent state, cross-instance memory, and a visual control surface, not a one-shot CLI prompt.

## Structural defects Cocoa fixes

Cocoa inherits the product logic of nodeskclaw, a prototype multi-agent workspace, and addresses three known structural defects from that prototype:

- **Near-neighbor messaging with explicit rings (D3).** The prototype used a flat 30-message log for context assembly, with no per-conversation filtering and a disabled topology check. Cocoa replaces this with near-neighbor-only messaging: nodes talk only to adjacent neighbors defined by their corridor. Collaboration happens through explicit rings, bounded mini-group-chats that keep context scoped and prevent the pollution that made the prototype's message bus unusable at scale.

- **Employee = preset/template with N isolated instances (D1).** The prototype coupled one employee identity to one running instance. If you needed two copies of the same reviewer in two different projects, you could not do it. Cocoa separates the employee (a persistent role identity: preset manifest plus shared memory) from the instance (a materialization in one office, with its own isolated workspace). One preset spawns many instances, each in its own office, each with its own PVC.

- **Preset system replacing engine selection (D5).** The prototype forced operators to choose a model engine (OpenCLaw, Hermes) at employee creation time. Cocoa replaces this with a preset system: you choose an AI persona (Planner, Worker, Oracle, Explorer, Reviewer) defined by a manifest of skills, tools, model, and prompt. The preset is the interface; the engine is an implementation detail. This is the difference between picking a car engine and picking a driver.

## What Cocoa adds beyond oh-my-openagent

oh-my-openagent provides the loop-engineering harness (boulder state, plan continuation, notepad, evidence ledger, compaction survival) that Cocoa ports. Cocoa adds four things that make it a different product:

- **Visual portal, not a CLI surface.** oh-my-openagent is a set of agent presets and harness mechanisms that run inside a coding agent's CLI session. Cocoa wraps the same harness in a web-based operator portal with per-employee command autocomplete, log panels, and topology visualization. You see your office, not a terminal scrollback.

- **Multi-human participation.** oh-my-openagent is single-operator. Cocoa supports multiple humans and multiple AI employees co-managing the same office. A human director approves and forwards; another human reviews; AI employees pass work along. All share the same blackboard, memory, and vault through permission-gated access.

- **Persistent, cross-instance shared memory.** oh-my-openagent's notepad is per-session. Cocoa's memory is per-employee and survives across instances, sessions, and compaction. Each employee accumulates experience as append-only memory entries. A `/distill` command consolidates memory into a learnable skill added to the employee's preset, closing the loop from experience to capability.

- **Skill-creating and the orchestration harness as differentiator.** The loop-engineering harness itself, ported from oh-my-openagent and extended, is Cocoa's core differentiator. Boulder state tracks long-running work across sessions. Plan continuation resumes interrupted plans. The evidence ledger records decisions and their rationale. The notepad captures learnings, issues, and problems. This is not a thin wrapper over an LLM API; it is a self-closing orchestration system that learns from its own execution.

## Reference comparison

| System | Scope | Operator | Messaging | Memory | Visual |
|--------|-------|----------|-----------|--------|--------|
| **nodeskclaw** | Multi-agent workspace (prototype) | Single human | Flat broadcast, polluted context | None | Web UI (basic) |
| **oh-my-openagent** | Agent presets + loop harness | Single human (CLI) | None (no multi-agent) | Per-session notepad | None |
| **Cocoa** | Multi-agent control studio | Multiple humans + AI team | Near-neighbor + rings, scoped | Per-employee, persistent, cross-instance | Web portal, debug-first |

## Who should adopt Cocoa

If you are running AI agents that need to collaborate across days, remember what they learned, and stay visible to a team of human operators, Cocoa is the control surface for that work.