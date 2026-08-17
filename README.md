# Eyot

> **Multi-agent control studio.** A control surface where humans plan, delegate, and observe a living cast of AI agents — from strategy to execution.

Eyot pairs a **React portal** with a **FastAPI backend** to give operators a single place to run multi-agent systems: summon reusable AI roles, specialize them into persistent identities, materialize them as running pods, watch them on a live topology canvas, and fold the lessons they learn back into new roles.

The name comes from an *eyot* — a small island in a river. It spells **E·Y·O·T**:

> **E**ntity · **Y**oke · **O**rganization · **T**opology — *bind bloodlines, yoke them into a continent, and map the territory.*

## The world

Eyot uses a nature / geography metaphor for its domain. Backend terms stay plain English and stable; the portal renders the 山海+生物 worldview:

| Layer | Backend | Portal |
|---|---|---|
| Tenant isolation | Organization | 大陆 (continent) |
| Scenario partition | Namespace | 区域 (region) |
| Concrete workstream | Workspace | 生境 (habitat) |
| Reusable role | BaseClass | 始祖 (ancestor) |
| Persistent identity | Entity | 血脉 (bloodline) |
| Running agent | Instance | 后裔 (descendant) |
| Neighbor link | Passage | 兽道 (wild path) |
| Live canvas | Topology | 领地地图 (territory map) |

The image: a continent of regions and habitats, populated by bloodlines and their descendants, connected by wild paths, all observable on a territory map.

## Architecture

Eyot is two products in one, held together by a control plane:

- **Control plane (Workspace)** — Portal + Harness Supervisor + deployment + observability. The operator's surface.
- **Agent runtime** — each 后裔 (Instance) is a sandboxed **pi**-driven loop in its own pod. No shared blind broadcast — agents talk only across 兽道 neighbors.

| Directory | Stack | Role |
|---|---|---|
| `eyot-backend/` | Python 3.12 · FastAPI · SQLAlchemy(async) · Alembic | API, domain, harness, deploy | 
| `eyot-portal/` | React 19 · Vite · TypeScript · Tailwind(v4) · Bun · Zustand | Operator UI |
| `eyot-artifacts/` | Dockerfile + K8s manifests | Container + deploy scaffolding |
| `eyot-instance-host/` | TypeScript · pi bridge | Outbound tunnel WS client for each Instance |

## Quick start

Prerequisites: Python ≥ 3.12 (+ [uv](https://docs.astral.sh/uv/)), [Bun](https://bun.sh) ≥ 1.2, PostgreSQL ≥ 16 (local or Docker).

```bash
./dev.sh           # backend (:4510) + portal (:5173), colored logs
./dev.sh --fresh   # force-rebuild .venv + node_modules first
```

### First-time database

```bash
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE eyot_dev;"
cd eyot-backend
cp .env.example .env    # set DATABASE_URL / JWT_SECRET / ENCRYPTION_KEY
uv run alembic upgrade head
```

On startup the app idempotently seeds the default 大陆, its default 区域, the built-in 始祖, permission atoms, and system capabilities — so a fresh database is immediately usable. Test databases (`eyot_test_*`) are created and torn down automatically by pytest.

Open the portal at `http://localhost:5173` (Swagger at `http://localhost:4510/docs`).

## Development

| Task | Command |
|---|---|
| Backend tests | `cd eyot-backend && uv run pytest` |
| Backend lint | `cd eyot-backend && uv run ruff check .` |
| Schema migration | `cd eyot-backend && uv run alembic upgrade head` |
| New migration | `cd eyot-backend && uv run alembic revision --autogenerate -m "..."` |
| Portal type-check | `cd eyot-portal && tsc -b` |
| Portal lint | `cd eyot-portal && bun run lint` |
| Portal build | `cd eyot-portal && bun run build` |
| Portal test | `cd eyot-portal && bun run test` |

The full contributor guide — including soft-delete and Alembic rules, the no-emoji rule, and Git conventions — lives in [`AGENTS.md`](AGENTS.md).

## Project layout

```
eyot/
├── eyot-backend/         # API + domain + harness (uv / FastAPI)
├── eyot-portal/          # Operator UI (Bun / Vite / React)
├── eyot-artifacts/       # Docker images + K8s manifests
├── eyot-instance-host/   # Per-instance tunnel bridge
├── docs/                 # Product SoT: roadmap, terminology, design
├── .omo/                 # Planning: executable plans, drafts, evidence
├── dev.sh                # One-command local dev launcher
├── AGENTS.md             # Contributor + agent guide
├── RELEASE_NOTES.md      # Changelog, per x.x
└── README.md
```

## Documentation

- [Roadmap & blueprint](docs/roadmap.md)
- [Terminology (code vs. portal naming)](docs/terminology.md)
- [API architecture](docs/api-architecture.md)
- [Release notes](RELEASE_NOTES.md)

## Versioning

Eyot versioning resets at 0.x for the pre-1.0 era and will tag from **1.0**. Releases are tracked in [`RELEASE_NOTES.md`](RELEASE_NOTES.md), per `x.x`; development builds (`x.y.z.devN`) fold into the section of the version they become.

## License

[Apache License 2.0](LICENSE)