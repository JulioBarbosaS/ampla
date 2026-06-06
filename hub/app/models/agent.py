from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.models.user import utcnow


class Agent(Base):
    """Agente de um usuário. PK é o slug público (ex: backend-julio).

    Settings vivem aqui e são a fonte de verdade — o daemon recebe cópia
    via hello_ack/settings_update (docs/ARCHITECTURE.md · Protocolo WS).
    """

    __tablename__ = "agents"

    slug: Mapped[str] = mapped_column(String(60), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    # Settings (defaults seguros — Ameaça 1: agente nasce em inbox, nunca auto)
    mode: Mapped[str] = mapped_column(String(10), default="inbox")  # inbox | auto
    allowed_senders: Mapped[list[str] | None] = mapped_column(JSON, default=None)  # None = todos
    max_auto_per_hour: Mapped[int] = mapped_column(default=10)
    auto_timeout_secs: Mapped[int] = mapped_column(default=120)
    instructions: Mapped[str] = mapped_column(Text, default="")


class AgentKey(Base):
    __tablename__ = "agent_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_slug: Mapped[str] = mapped_column(ForeignKey("agents.slug"), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # sha256 hex
    label: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
