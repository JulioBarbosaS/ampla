from datetime import datetime

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.models.user import utcnow


class Message(Base):
    """Mensagem entre agentes. from/to por slug (slugs nunca são reciclados:
    agente revogado mantém o slug reservado).

    Threading (inspirado no Agent Messaging Protocol): thread_id aponta
    para a raiz da conversa; in_reply_to para a mensagem respondida.
    """

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation", "from_agent", "to_agent", "created_at"),
        Index("ix_messages_pending", "to_agent", "delivered_at"),
        Index("ix_messages_thread", "thread_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_agent: Mapped[str] = mapped_column(String(60))
    to_agent: Mapped[str] = mapped_column(String(60))
    body: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(16), default="request")
    priority: Mapped[str] = mapped_column(String(8), default="normal")
    # Origem em fan-out de grupo: "@frontend-team" ou "@all" (None = DM direta)
    group_slug: Mapped[str | None] = mapped_column(String(61), default=None)
    thread_id: Mapped[int | None] = mapped_column(default=None)  # id da raiz da thread
    in_reply_to: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)  # TTL pendente
