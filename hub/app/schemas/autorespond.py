from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AutorespondRunOut(BaseModel):
    """One stored auto-respond run, for the agent's 'Atividade automática' tab."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_slug: str
    trigger_message_id: int | None
    from_sender: str
    result: str
    reason: str | None
    reply_preview: str
    tools_allowed: str
    tools_disallowed: str
    guardrails: dict
    duration_ms: int
    timed_out: bool
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    created_at: datetime
