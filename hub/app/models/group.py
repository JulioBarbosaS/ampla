from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.models.user import utcnow


class Group(Base):
    """Grupo de agentes (ex: frontend-team). Slug em namespace próprio —
    colisão com slug de agente é proibida na criação (e vice-versa).
    "all" é reservado para o broadcast virtual."""

    __tablename__ = "groups"

    slug: Mapped[str] = mapped_column(String(60), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class GroupMember(Base):
    __tablename__ = "group_members"

    group_slug: Mapped[str] = mapped_column(
        ForeignKey("groups.slug", ondelete="CASCADE"), primary_key=True
    )
    agent_slug: Mapped[str] = mapped_column(ForeignKey("agents.slug"), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
