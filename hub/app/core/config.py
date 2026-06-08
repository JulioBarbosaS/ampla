"""Hub configuration via environment variables (AMP_ prefix)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-secret-change-me"  # noqa: S105 — sentinel; production refuses to boot with it


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AMP_", env_file=".env", extra="ignore")

    environment: str = "dev"  # dev | production
    database_url: str = "sqlite+aiosqlite:///./amp.db"
    # Built web panel (web/dist). When set and present, the hub serves the UI
    # at the same origin as the API — one URL, no CORS (GitLab-style install).
    web_dist: str | None = None

    jwt_secret: str = DEV_JWT_SECRET
    jwt_expires_days: int = 7

    invite_expires_hours: int = 48
    pending_ttl_days: int = 7  # an undelivered message expires (excluded from the flush)

    # Security limits (see docs/ARCHITECTURE.md · Threats 2 and 3)
    login_max_attempts: int = 5  # per account, before incremental lockout
    login_lockout_base_secs: int = 30  # doubles on each consecutive lockout
    login_rate_per_minute: int = 20  # per IP, on auth routes
    ws_hello_timeout_secs: int = 10
    ws_heartbeat_secs: float = 30.0  # ping every N s; 2 cycles without a reply ⇒ drop
    ws_max_frame_bytes: int = 64 * 1024
    message_max_body_bytes: int = 16 * 1024
    ws_messages_per_minute: int = 60  # per-connection token bucket
    broadcast_per_minute: int = 5  # @group/@all fan-outs per agent (anti-spam)

    cors_origins: list[str] = ["http://localhost:5173"]

    def validate_for_environment(self) -> None:
        """Production refuses to boot with a default or weak secret (Threat 2)."""
        if self.environment != "production":
            return
        if self.jwt_secret == DEV_JWT_SECRET:
            raise RuntimeError(
                "AMP_JWT_SECRET obrigatório em produção — recusando subir com secret default."
            )
        if len(self.jwt_secret.encode()) < 32:
            raise RuntimeError(
                "AMP_JWT_SECRET precisa de no mínimo 32 bytes (RFC 7518 §3.2 para HS256)."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
