"""Protocolo WebSocket — definição canônica.

ESPELHO: bridge/src/shared/protocol.ts. Alterou aqui, altera lá NO MESMO COMMIT
(docs/ARCHITECTURE.md · Protocolo WebSocket).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from app.schemas.agent import AgentSettings
from app.schemas.message import PRIORITY_PATTERN, TYPE_PATTERN, MessageOut

# ---------- cliente → hub ----------


class HelloFrame(BaseModel):
    """Primeiro frame obrigatório. Daemon usa (agent_id, key); painel usa jwt."""

    type: Literal["hello"] = "hello"
    agent_id: str | None = None
    key: str | None = None
    jwt: str | None = None


class SendMessageFrame(BaseModel):
    type: Literal["message"] = "message"
    to: str
    body: str = Field(min_length=1)
    msg_type: str = Field(default="request", pattern=TYPE_PATTERN)
    priority: str = Field(default="normal", pattern=PRIORITY_PATTERN)
    in_reply_to: int | None = None


ClientFrame = Annotated[HelloFrame | SendMessageFrame, Field(discriminator="type")]
client_frame_adapter: TypeAdapter[ClientFrame] = TypeAdapter(ClientFrame)

# ---------- hub → cliente ----------


class GroupInfo(BaseModel):
    slug: str
    display_name: str
    members: list[str]


class HelloAckFrame(BaseModel):
    type: Literal["hello_ack"] = "hello_ack"
    agent_id: str | None  # None para conexões de painel (observer)
    online: list[str]
    settings: AgentSettings | None  # None para observers
    pending: list[MessageOut]
    groups: list[GroupInfo] = []


class MessageDeliveryFrame(BaseModel):
    type: Literal["message"] = "message"
    message: MessageOut


class DeliveredFrame(BaseModel):
    type: Literal["delivered"] = "delivered"
    message_id: int
    to: str


class PresenceFrame(BaseModel):
    type: Literal["presence"] = "presence"
    agent_id: str
    status: Literal["online", "offline"]


class SettingsUpdateFrame(BaseModel):
    type: Literal["settings_update"] = "settings_update"
    settings: AgentSettings


class BroadcastResultFrame(BaseModel):
    """Devolvido ao remetente após fan-out de @grupo/@all."""

    type: Literal["broadcast_result"] = "broadcast_result"
    group: str
    sent: list[str]
    skipped: list[str]  # bloqueados pela allowlist do destinatário
    offline: list[str]  # receberão como pendente na reconexão


class ErrorFrame(BaseModel):
    type: Literal["error"] = "error"
    code: str
    detail: str


ServerFrame = (
    HelloAckFrame
    | MessageDeliveryFrame
    | DeliveredFrame
    | PresenceFrame
    | SettingsUpdateFrame
    | BroadcastResultFrame
    | ErrorFrame
)
