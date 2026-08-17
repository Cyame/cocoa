# Eyot Backend

FastAPI + SQLAlchemy async + Alembic backend service.

## Development Databases

The backend uses **two separate databases** on a local PostgreSQL (>= 16):

| Database | Purpose | Managed by |
|----------|---------|------------|
| `eyot_dev` | Development schema + your manual data | **Alembic only** (`alembic upgrade head`) |
| `eyot_test_template` | pytest template (session-scoped) | `tests/conftest.py` |
| `eyot_test_<hex>` | pytest per-test clone | `tests/conftest.py` |

**pytest never touches `eyot_dev`.** Every DB-touching test clones a private database from `eyot_test_template` (built once per session by Alembic) and drops it afterwards. Data in `eyot_dev` is always safe. Never put a `eyot_dev` connection string in test code.

### First-time setup

```bash
# Using an existing local Postgres (default: postgres/postgres @ 5432)
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE eyot_dev;"

# Configure and apply schema
cp .env.example .env   # set DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/eyot_dev
uv run alembic upgrade head
```

Connection strings:

- Dev (Alembic + app): `postgresql+asyncpg://postgres:postgres@localhost:5432/eyot_dev`
- Test: managed entirely by conftest (template + per-test clones)

### Fallback: disposable container

If you don't have a local Postgres, start one on port 5433 (avoids clashing with an existing 5432):

```bash
docker compose -f docker-compose.dev.yml up -d
# then create the two databases inside it and adjust .env / conftest ports
docker compose -f docker-compose.dev.yml down -v   # stop and remove data
```

## Tests

```bash
uv run pytest          # full suite (uses eyot_test)
uv run ruff check .    # lint
```

## Migrations

```bash
uv run alembic upgrade head                              # apply
uv run alembic downgrade base                            # roll back all
uv run alembic revision --autogenerate -m "message"      # new migration after model changes
```
