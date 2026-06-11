from pydantic import BaseModel


class KillSwitchState(BaseModel):
    """Current global auto-responder state (GET /api/admin/kill-switch)."""

    auto_responder_enabled: bool


class KillSwitchUpdate(BaseModel):
    """Flip the global kill switch. enabled=False suspends ALL auto-responders."""

    enabled: bool
