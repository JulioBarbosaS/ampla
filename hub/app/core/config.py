"""Configuração do hub via variáveis de ambiente (prefixo AMP_)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AMP_", env_file=".env", extra="ignore")

    environment: str = "dev"  # dev | production
    database_url: str = "sqlite+aiosqlite:///./amp.db"

    jwt_secret: str = DEV_JWT_SECRET
    jwt_expires_days: int = 7

    invite_expires_hours: int = 48

    # Limites de segurança (ver docs/ARCHITECTURE.md · Ameaças 2 e 3)
    login_max_attempts: int = 5  # por conta, antes do lockout incremental
    login_lockout_base_secs: int = 30  # dobra a cada lockout consecutivo
    login_rate_per_minute: int = 20  # por IP, em rotas de auth
    ws_hello_timeout_secs: int = 10
    ws_max_frame_bytes: int = 64 * 1024
    message_max_body_bytes: int = 16 * 1024
    ws_messages_per_minute: int = 60  # token bucket por conexão

    cors_origins: list[str] = ["http://localhost:5173"]

    def validate_for_environment(self) -> None:
        """Produção recusa subir com secret default ou fraco (Ameaça 2)."""
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
