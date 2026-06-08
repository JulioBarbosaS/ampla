from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.models.user import utcnow


class Group(Base):
    """A group of agents (e.g. frontend-team). Slug in its own namespace —
    collision with an agent slug is forbidden at creation (and vice versa).
    "all" is reserved for the virtual broadcast."""

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
