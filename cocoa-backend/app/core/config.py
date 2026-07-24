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

    # ── JWT ──────────────────────────────────────────────
    JWT_SECRET: str = ""

    # ── Encryption ───────────────────────────────────────
    ENCRYPTION_KEY: str = ""


settings = Settings()
