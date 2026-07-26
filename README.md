# Cocoa

**Multi-agent control studio.** A workspace where humans orchestrate AI agents -- from strategy to execution.

Cocoa is a control surface for running multi-agent systems. A web portal pairs with a Python backend to give operators a single place to plan, delegate, and observe AI-driven work. The backend has its **P2 core domain** in place (13 models — 12 business + 1 audit Event — Alembic migrations, pytest harness), **P3 API architecture** (RESTful URL rules, middleware pipeline, error envelope, pagination, OpenAPI), **P4 Agent Presets** (preset manifest schema, 6 built-in presets, CRUD API, in-memory registry, JWT auth), **P5 messaging** (neighbor-only delivery, corridor CRUD, directive routing, activation triggers), **P6 blackboard + storage + vault + memory** (virtual filesystem, vault archiving, append-only memory entries, office-scoped permissions), and **P7 instance runtime** (lifecycle state machine with 7 statuses, Stripe-style action endpoints, K8s deployment scaffolding, Langfuse integration reservation). A **P7.5 fix-and-sync wave** landed the P8-plan review findings (handler DB-write prohibition, proxy_token-in-payload, permission model simplification, response schemas, lifespan daily-report wiring, test isolation) plus P7 implementation corrections (DELETE `previous_status` capture, list/get office authorization, Membership cascade soft-delete, workspace_path 409 mapping, past-tense event naming) and full documentation sync. 249 tests pass; ruff is clean. The portal is a P1.5 scaffold (React 19 + Vite 8 + Bun + Tailwind v4 + RouterProvider接入 — P0 UI in place). API routes live at `/api/v1/` with `Auth`, `EmployeePresets`, `Employees`, `Offices`, `Instances`, `Messaging`, `Blackboard` (with BlackboardFile + Vault sub-resources), `Memory`, and `Learning` (stub for P10).

## Status

| Component | State |
|-----------|-------|
| `cocoa-backend/` | P7 instance runtime & deployment scaffolding on top of P6 blackboard & storage & vault & messaging on top of P3.5 observability; P7.5 fix-and-sync wave landed (audit + doc sync) |
| `cocoa-portal/`  | P1.5 scaffold (React 19 + Vite 8 + Tailwind CSS v4 + Bun, RouterProvider wired, single Index page placeholder) |
| `cocoa-artifacts/` | P7 Instance runtime Dockerfile and K8s manifests (Deployment, Service, ConfigMap, PVC, NetworkPolicy) |
| CI | Baseline (lint + build on push/PR) |

## Project Layout

```
cocoa/
├── cocoa-backend/      # API server -- Python 3.12 + FastAPI + SQLAlchemy
├── cocoa-portal/       # Web portal -- React 19 + Vite 8 + TypeScript + Bun + Tailwind CSS v4
├── cocoa-artifacts/    # Docker images & deploy manifests (P7)
├── .omo/               # Plans, drafts, run-continuation state
├── .github/            # CI workflows
├── .codegraph/         # Code-graph index (machine-local, git-ignored)
├── dev.sh              # One-command local dev launcher
├── AGENTS.md           # Agent / contributor dev guide
└── README.md           # This file
```

## Build-context note

**The backend builds from `cocoa-backend/`, not the repo root.** `pyproject.toml` and `alembic.ini` live in `cocoa-backend/`. Run `uv sync` and `alembic` from inside that directory, or use `dev.sh` which handles the `cd` for you. The same applies to the portal: `bun install` and `bun run dev` are meant to be run from `cocoa-portal/`.

## Prerequisites

| Dependency                                        | Purpose                              |
| ------------------------------------------------- | ------------------------------------ |
| Python >= 3.12 + [uv](https://docs.astral.sh/uv/) | Backend runtime & package manager    |
| Bun >= 1.2                                       | Frontend runtime & package manager    |
| PostgreSQL >= 16 (local or Docker)                | Backend database (dev + test)        |

## Database setup (first time only)

The backend uses `cocoa_dev` on your local PostgreSQL for development (Alembic-managed). Test databases (`cocoa_test_template` + per-test clones) are created and destroyed automatically by the pytest harness.

```bash
# Create the dev database (adjust user/host to your local Postgres)
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE cocoa_dev;"

# Apply the schema
cd cocoa-backend
cp .env.example .env   # then set DATABASE_URL=postgresql+asyncpg://<user>:<pass>@localhost:5432/cocoa_dev
uv run alembic upgrade head
```

A `docker-compose.dev.yml` is also available in `cocoa-backend/` if you prefer a disposable container (runs on port 5433 to avoid clashing with an existing local Postgres).

## Quick Start

```bash
./dev.sh              # Start backend (4510) + portal (5173) with colored logs
./dev.sh --fresh      # Force reinstall .venv and node_modules first
```

`dev.sh` runs the backend (`uv run uvicorn`) and the portal (`bun run dev`) in the background, prefixes each line of output with `[BACKEND]` or `[PORTAL]` so you can tell streams apart, and cleans up both children on `Ctrl+C`.

### Manual start (alternative)

**Backend:**

```bash
cd cocoa-backend
uv sync
cp .env.example .env        # then fill in DATABASE_URL, JWT_SECRET, ENCRYPTION_KEY
uv run uvicorn app.main:app --reload --port 4510
```

API at `http://localhost:4510` | Swagger at `http://localhost:4510/docs`.

**Frontend (Portal):**

```bash
cd cocoa-portal
bun install
bun run dev
```

Portal at `http://localhost:5173` (Vite default) | `/api` auto-proxies to the backend.

## Development

| Task | Command |
|------|---------|
| Backend lint        | `cd cocoa-backend && uv run ruff check .` |
| Backend tests       | `cd cocoa-backend && uv run pytest` |
| Backend migration   | `cd cocoa-backend && uv run alembic upgrade head` |
| New migration       | `cd cocoa-backend && uv run alembic revision --autogenerate -m "..."` |
| Frontend type-check | `cd cocoa-portal && tsc -b` |
| Frontend lint       | `cd cocoa-portal && bun run lint` |
| Frontend build      | `cd cocoa-portal && bun run build` |
| Frontend test       | `cd cocoa-portal && bun run test` |
| Lint everything     | see `AGENTS.md` |

See [AGENTS.md](AGENTS.md) for the full development guide, including soft-delete and Alembic rules, the no-emoji rule, and Git conventions.

## License

[Apache License 2.0](LICENSE)
