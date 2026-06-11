from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class HubState(Base):
    """Singleton row (id is always 1) holding instance-wide runtime flags.

    Persisted so a restart can't silently undo a kill switch an admin engaged —
    the global brake outlives the process (docs/specs/03-autorespond-trust.md).
    """

    __tablename__ = "hub_state"

    id: Mapped[int] = mapped_column(primary_key=True)  # always 1

    # Global kill switch (Epic 03 · 3.2): when False, NO agent auto-responds,
    # instance-wide. Default True = normal operation.
    auto_responder_enabled: Mapped[bool] = mapped_column(default=True)
