from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_slug: str
    trigger_message_id: int | None
    to_agent: str
    draft_body: str
    status: str
    decided_by: int | None
    decided_at: datetime | None
    created_at: datetime


class ApprovalDecision(BaseModel):
    """Owner's call on a pending approval. `approve` sends the draft as the
    agent; pass `body` to edit before sending (status becomes `edited`)."""

    decision: str = Field(pattern=r"^(approve|reject)$")
    body: str | None = Field(default=None, min_length=1, max_length=16384)
