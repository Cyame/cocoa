# Eyot

**Multi-agent control studio.** A workspace where humans orchestrate AI agents -- from strategy to execution.

Eyot is a control surface for running multi-agent systems. A web portal pairs with a Python backend to give operators a single place to plan, delegate, and observe AI-driven work.

**Direction / blueprint**: [`docs/roadmap.md`](docs/roadmap.md) · **Active PRD**: [`docs/prd-v2.md`](docs/prd-v2.md) · **Frozen MVP PRD**: [`docs/prd-v1.md`](docs/prd-v1.md) · **Contributor guide**: [`AGENTS.md`](AGENTS.md)

The backend has its **P2 core domain** in place (17 models — 12 business (P2) + 1 audit Event (P3.5) + 1 loop state (P8) + 1 corridor node (P9) + 1 deploy record (P11b) + 1 instance provider config (P14a) — Alembic migrations, pytest harness), **P3 API architecture** (RESTful URL rules, middleware pipeline, error envelope, pagination, OpenAPI), **P4 Agent Presets** (preset manifest schema, 6 built-in presets, CRUD API, in-memory registry, JWT auth), **P5 messaging** (neighbor-only delivery, corridor CRUD, directive routing, activation triggers), **P6 blackboard + storage + vault + memory** (virtual filesystem, vault archiving, append-only memory entries, office-scoped permissions), **P7 instance runtime** (lifecycle state machine with 7 statuses, Stripe-style action endpoints, K8s deployment scaffolding, Langfuse integration reservation), and **P8 harness + control plane** (Boulder loop engine + in-memory Harness Supervisor with 4 deterministic circuit breakers + 5 control command actions on `/instances/{id}/{interrupt,pause,resume,status,snapshot}` + P5 activation consumer + idle-check continuation engine + append-only notepad + todo-completion enforcer for `boulder_snapshot`). A **P7.5 fix-and-sync wave** landed the P8-plan review findings (handler DB-write prohibition, proxy_token-in-payload, permission model simplification, response schemas, lifespan daily-report wiring, test isolation) plus P7 implementation corrections (DELETE `previous_status` capture, list/get office authorization, Membership cascade soft-delete, workspace_path 409 mapping, past-tense event naming) and full documentation sync. 425 backend tests pass (P14a verified); 6 stale-by-design failures + 3 skips documented in .omo/evidence/eyot-vs-nodeskclaw-drift.md; ruff is clean. The portal is a P10 first UI: 8 pages (Login / Office list / Office detail / Instance detail / Composer / Debug / Topology viz / Employee Learning), SVG-based topology canvas with glow + pan/zoom + 3 interaction modes (Select/Connect/Move) + CorridorNode canvas elements + message flow animation, plus the P10 Learning page (memory summary + distill form + result modal). API routes live at `/api/v1/` with `Auth`, `EmployeePresets`, `Employees`, `Offices`, `Instances` (5 new harness control actions: interrupt / pause / resume / status / snapshot), `Messaging`, `Blackboard` (with BlackboardFile + Vault sub-resources), `Memory`, and `Learning` (3 endpoints: memory summary, skill distill, preset fetch). Subsequent waves (P11–P15f) added real K8s deploy, LLM providers, orbstack live env, 15d naming, PRD-v1 implementation, and PRD-v2 as the next target — see `docs/roadmap.md`.

## Status

| Component | State |
|-----------|-------|
| `eyot-backend/` | P14a real LLM: LLMClient (4 provider types: openai-compatible / openai-responses / anthropic / custom) + ProviderRouter + ModelCatalog (models.dev + 600s cache + builtin fallback) + InstanceProviderConfig + LLMDistiller — on top of P13 doc sync + P12 K8s manifests + P11c DeployService + EventWatcher + internal endpoints (events/emit + control/poll) + K8s-mode agent_runtime + 2 P0 fixes (blackboard/memory writers + proxy_token K8s env injection) + P11b resource_builder + event_bus + DeployRecord + P11a K8sClient + client_manager + P10 learning + P9 portal backend + P8 harness + P7 runtime + P7.5 fix-and-sync |
| `eyot-portal/`  | P10 Learning page + P9 first UI (7 pages + topology viz + CorridorNode + 3 interaction modes + zero new npm deps) |
| `eyot-artifacts/` | P7 Instance runtime Dockerfile and K8s manifests (Deployment, Service, ConfigMap, PVC, NetworkPolicy) |
| CI | Baseline (lint + build on push/PR) |

## Project Layout

```
eyot/
├── eyot-backend/      # API server -- Python 3.12 + FastAPI + SQLAlchemy
├── eyot-portal/       # Web portal -- React 19 + Vite 8 + TypeScript + Bun + Tailwind CSS v4
├── eyot-artifacts/    # Docker images & deploy manifests (P7)
├── docs/               # Product SoT: roadmap.md + prd-v*.md + subsystem contracts
├── .omo/               # Executable plans + drafts + evidence (roadmaps archived under plans/archive/)
├── .github/            # CI workflows
├── .codegraph/         # Code-graph index (machine-local, git-ignored)
├── dev.sh              # One-command local dev launcher
├── AGENTS.md           # Agent / contributor dev guide
└── README.md           # This file
```

## Build-context note

**The backend builds from `eyot-backend/`, not the repo root.** `pyproject.toml` and `alembic.ini` live in `eyot-backend/`. Run `uv sync` and `alembic` from inside that directory, or use `dev.sh` which handles the `cd` for you. The same applies to the portal: `bun install` and `bun run dev` are meant to be run from `eyot-portal/`.

## Prerequisites

| Dependency                                        | Purpose                              |
| ------------------------------------------------- | ------------------------------------ |
| Python >= 3.12 + [uv](https://docs.astral.sh/uv/) | Backend runtime & package manager    |
| Bun >= 1.2                                       | Frontend runtime & package manager    |
| PostgreSQL >= 16 (local or Docker)                | Backend database (dev + test)        |

## Database setup (first time only)

The backend uses `eyot_dev` on your local PostgreSQL for development (Alembic-managed). Test databases (`eyot_test_template` + per-test clones) are created and destroyed automatically by the pytest harness.

```bash
# Create the dev database (adjust user/host to your local Postgres)
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE eyot_dev;"

# Apply the schema
cd eyot-backend
cp .env.example .env   # then set DATABASE_URL=postgresql+asyncpg://<user>:<pass>@localhost:5432/eyot_dev
uv run alembic upgrade head
```

A `docker-compose.dev.yml` is also available in `eyot-backend/` if you prefer a disposable container (runs on port 5433 to avoid clashing with an existing local Postgres).

## Quick Start

```bash
./dev.sh              # Start backend (4510) + portal (5173) with colored logs
./dev.sh --fresh      # Force reinstall .venv and node_modules first
```

`dev.sh` runs the backend (`uv run uvicorn`) and the portal (`bun run dev`) in the background, prefixes each line of output with `[BACKEND]` or `[PORTAL]` so you can tell streams apart, and cleans up both children on `Ctrl+C`.

### Manual start (alternative)

**Backend:**

```bash
cd eyot-backend
uv sync
cp .env.example .env        # then fill in DATABASE_URL, JWT_SECRET, ENCRYPTION_KEY
uv run uvicorn app.main:app --reload --port 4510
```

API at `http://localhost:4510` | Swagger at `http://localhost:4510/docs`.

**Frontend (Portal):**

```bash
cd eyot-portal
bun install
bun run dev
```

Portal at `http://localhost:5173` (Vite default) | `/api` auto-proxies to the backend.

### Portal walkthrough

After `./dev.sh`, open `http://localhost:5173` and follow this path to explore the P9 Portal:

1. **Login** — Register or sign in at `/login`. JWT is persisted to `localStorage` (key `eyot.session`). Redirects to office list on success.
2. **Office list** — `/offices` shows a card grid of accessible offices with member and instance counts. Click any card to enter.
3. **Office detail** — `/offices/:id` has 3 tabs: Employees (lists memberships with roles), Instances (running agents), and Blackboard (shared state). Each instance row links to instance detail.
4. **Topology** — `/offices/:id/topology` is the flagship SVG canvas. Nodes are rendered as circles with real-time glow halos reflecting their `loop_status` (green=strong=running, yellow=medium=idle, red=strong=failed, etc.). Position is free-form Cartesian `(posx, posy)`. Corridor lines connect nodes. A 3-mode toolbar (Select `V` / Connect `C` / Move `M`) switches interaction behavior. Drag nodes in Move mode; create corridors in Connect mode. Live-status polls every 2 seconds.
5. **Instance control** — `/offices/:id/instances/:iid` shows an agent's status bar, 5 harness control buttons (Interrupt / Pause / Resume / Status / Snapshot), and a scrollable event panel. Boulder snapshot modal shows the last checkpoint.
6. **Composer** — `/offices/:id/composer` is a multi-recipient message editor. Type `@slug /command` to segment text into per-recipient compartments with slash command autocomplete (press `/` to see available commands: global, control, and per-preset).
7. **Debug** — `/debug` is the raw audit event stream. Filter by type prefix (e.g. `harness.`), resource type, resource ID, request ID, or date range. Events poll every 5 seconds. Export to JSON with one click.

For architecture details, see [docs/portal-system.md](docs/portal-system.md).

### Quick start: distill a skill

P10 Learning converts accumulated employee memory into reusable agent presets. Here is the flow:

1. **Browse memory summary** — Navigate to `/employees/:id/learning` in the portal. The page shows per-kind memory counts (experience / lesson / decision / problem) and recent lesson snippets.
2. **Trigger distillation** — Enter a kebab-case `target_skill_slug` (e.g. `debugging-checklist`), optionally select memory kind filters, and click "Distill". The system runs the `AggregatingDistiller` heuristic engine (no LLM) to extract commands, skills, and a prompt from the employee's memory.
3. **Preview manifest** — A modal shows the generated manifest (model, prompt, skills, tools, commands) before committing. Confirm to create a new `EmployeePreset` with slug `{source}-skill-{target}`.
4. **Assign to employees** — The new preset appears in the preset list and can be assigned to any employee for future instances.

For the API equivalent:

```bash
# View memory summary
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:4510/api/v1/learning/memories/$EMPLOYEE_ID/summary

# Distill into a new preset (returns 201 with manifest preview)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_skill_slug": "my-skill", "source_preset_slug": "base-preset"}' \
  http://localhost:4510/api/v1/learning/employees/$EMPLOYEE_ID/distill
```

Full docs at [docs/learning-system.md](docs/learning-system.md).

## Development

| Task | Command |
|------|---------|
| Backend lint        | `cd eyot-backend && uv run ruff check .` |
| Backend tests       | `cd eyot-backend && uv run pytest` |
| Backend migration   | `cd eyot-backend && uv run alembic upgrade head` |
| New migration       | `cd eyot-backend && uv run alembic revision --autogenerate -m "..."` |
| Frontend type-check | `cd eyot-portal && tsc -b` |
| Frontend lint       | `cd eyot-portal && bun run lint` |
| Frontend build      | `cd eyot-portal && bun run build` |
| Frontend test       | `cd eyot-portal && bun run test` |
| Lint everything     | see `AGENTS.md` |

See [AGENTS.md](AGENTS.md) for the full development guide, including soft-delete and Alembic rules, the no-emoji rule, and Git conventions.

## License

[Apache License 2.0](LICENSE)
