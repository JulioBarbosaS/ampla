from datetime import datetime

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.models.user import utcnow


class AuditLog(Base):
    """Trilha de auditoria (docs/ARCHITECTURE.md · Segurança · Transversal).

    Eventos: login_ok, login_fail, login_locked, setup, register,
    invite_created, agent_created, key_created, key_revoked,
    settings_changed, message_blocked_allowlist, ws_auth_fail.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    event: Mapped[str] = mapped_column(String(40), index=True)
    actor: Mapped[str] = mapped_column(String(120), default="")  # email, slug ou ip
    detail: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
