from datetime import datetime

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.models.user import utcnow


class Message(Base):
    """Mensagem entre agentes. from/to por slug (slugs nunca são reciclados:
    agente revogado mantém o slug reservado)."""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation", "from_agent", "to_agent", "created_at"),
        Index("ix_messages_pending", "to_agent", "delivered_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_agent: Mapped[str] = mapped_column(String(60))
    to_agent: Mapped[str] = mapped_column(String(60))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
