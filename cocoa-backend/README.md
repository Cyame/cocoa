# Cocoa Backend

FastAPI + SQLAlchemy async + Alembic backend service.

## Development Database

Start a local PostgreSQL 16 instance for development:

```bash
docker compose -f docker-compose.dev.yml up -d
```

Credentials: `postgresql://cocoa:cocoa@localhost:5433/cocoa_dev`

Stop the database:

```bash
docker compose -f docker-compose.dev.yml down
```

To also remove the data volume:

```bash
docker compose -f docker-compose.dev.yml down -v
```
