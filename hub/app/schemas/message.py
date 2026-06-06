from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MessageOut(BaseModel):
    """Mensagem como trafega no REST e no WS (campo `from` é alias)."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    from_agent: str = Field(serialization_alias="from", validation_alias="from_agent")
    to_agent: str = Field(serialization_alias="to", validation_alias="to_agent")
    body: str
    created_at: datetime
    delivered_at: datetime | None


class ConversationPartner(BaseModel):
    """Item da lista de conversas (sidebar do painel)."""

    agent: str
    last_message: MessageOut
