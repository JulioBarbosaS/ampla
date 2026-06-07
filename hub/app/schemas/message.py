from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Tipos e prioridades (subconjunto do Agent Messaging Protocol)
TYPE_PATTERN = r"^(request|response|notification|task|alert|status|ack)$"
PRIORITY_PATTERN = r"^(urgent|high|normal|low)$"


class MessageOut(BaseModel):
    """Mensagem como trafega no REST e no WS (campo `from` é alias)."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    from_agent: str = Field(serialization_alias="from", validation_alias="from_agent")
    to_agent: str = Field(serialization_alias="to", validation_alias="to_agent")
    body: str
    type: str
    priority: str
    group: str | None = Field(
        default=None, serialization_alias="group", validation_alias="group_slug"
    )
    thread_id: int | None
    in_reply_to: int | None
    created_at: datetime
    delivered_at: datetime | None
    expires_at: datetime | None


class ConversationPartner(BaseModel):
    """Item da lista de conversas (sidebar do painel)."""

    agent: str
    last_message: MessageOut
