"""Application settings loaded from environment variables.

P0 stub. Real defaults and validators land in P1/P2 alongside the first
models and auth routes.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cocoa backend configuration.

    Values are loaded from environment variables (and a local ``.env`` if
    present). All three keys are required by the deployment but the
    P0 stub ships empty defaults so the app can boot for ``/health``
    smoke tests without a populated ``.env``.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Database ─────────────────────────────────────────
    DATABASE_URL: str = ""
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # ── JWT ──────────────────────────────────────────────
    JWT_SECRET: str = ""

    # ── Encryption ───────────────────────────────────────
    ENCRYPTION_KEY: str = ""

    # ── Runtime environment ──────────────────────────────
    # "dev" exposes /api/v1/error-test and tracebacks in error responses.
    ENV: str = "dev"

    # ── Logging ──────────────────────────────────────────
    # Applied by configure_logging() at startup. dev gets human-readable stderr
    # with color; non-dev gets JSON to stdout.
    LOG_LEVEL: str = "INFO"

    # ── CORS ─────────────────────────────────────────────
    # Dev default allows all origins; tighten per-environment in P8+.
    CORS_ALLOWED_ORIGINS: list[str] = ["*"]

    # ── Langfuse ──────────────────────────────────────────
    # Langfuse integration (P8 agent runtime reads from instance runtime_config)
    # LANGFUSE_PUBLIC_KEY: str = ""
    # LANGFUSE_SECRET_KEY: str = ""
    # LANGFUSE_HOST: str = ""

    # ── Fornix mount mirror (v4.5, H3) ────────────────────
    # Root of the Host shared-mount tree. The backend dual-writes every
    # FornixFile into <FORNIX_ROOT>/<workspace_id>/shared/ so instance pods
    # (which mount that directory at /data/shared) see the same view.
    FORNIX_ROOT: str = "/var/cocoa/workspaces"


settings = Settings()
