# Cocoa

**Multi-agent control studio.** A workspace where humans orchestrate AI agents -- from strategy to execution.

Cocoa is a control surface for running multi-agent systems. A web portal pairs with a Python backend to give operators a single place to plan, delegate, and observe AI-driven work. This repository is the **P0 scaffold** -- the empty house ready for P1+ feature work. No business logic yet.

## Status

| Component | State |
|-----------|-------|
| `cocoa-backend/` | P0 scaffold (FastAPI + uv + Alembic) |
| `cocoa-portal/`  | P0 scaffold (React 19 + Vite 6 + Tailwind CSS v4 + Bun) |
| `cocoa-artifacts/` | Placeholder (Docker images & K8s manifests come in P7) |
| CI | Baseline (lint + build on push/PR) |

## Project Layout

```
cocoa/
├── cocoa-backend/      # API server -- Python 3.12 + FastAPI + SQLAlchemy
├── cocoa-portal/       # Web portal -- React 19 + Vite 6 + TypeScript + Bun + Tailwind CSS v4
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
| Frontend type-check | `cd cocoa-portal && tsc -b` |
| Frontend lint       | `cd cocoa-portal && bun run lint` |
| Frontend build      | `cd cocoa-portal && bun run build` |
| Frontend test       | `cd cocoa-portal && bun run test` |
| Lint everything     | see `AGENTS.md` |

See [AGENTS.md](AGENTS.md) for the full development guide, including soft-delete and Alembic rules, the no-emoji rule, and Git conventions.

## License

[Apache License 2.0](LICENSE)
