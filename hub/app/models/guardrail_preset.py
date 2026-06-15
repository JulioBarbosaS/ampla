from datetime import datetime

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base, UTCDateTime
from app.models.user import utcnow


class GuardrailPreset(Base):
    """A named bundle of guardrail/auto settings that can be applied to an agent
    (Epic 04 · 4.1). v1 is apply-and-detach: applying copies the fields onto the
    agent (no live link).

    owner_id null = a built-in/global preset (admin-managed, seeded at startup).
    Security: presets centralize the most dangerous knobs (trusted_senders,
    allow_write) — applying a permissive one is audited.
    """

    __tablename__ = "guardrail_presets"
    __table_args__ = (Index("ix_presets_owner_name", "owner_id", "name", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None, index=True)
    name: Mapped[str] = mapped_column(String(60))
    settings: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
