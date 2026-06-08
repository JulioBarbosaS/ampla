"""WebSocket protocol — canonical definition.

MIRROR: bridge/src/shared/protocol.ts. Change it here, change it there IN THE SAME COMMIT
(docs/ARCHITECTURE.md · WebSocket protocol).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from app.schemas.agent import AgentSettings
from app.schemas.message import PRIORITY_PATTERN, TYPE_PATTERN, MessageOut

# ---------- client → hub ----------


class HelloFrame(BaseModel):
    """First required frame. The daemon uses (agent_id, key); the panel uses jwt."""

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


class AckFrame(BaseModel):
    """Receipt confirmation (at-least-once). The daemon sends it once it stores the
    message locally; only then does the hub mark `delivered_at` and notify the
    sender. Without the ack, the message comes back in the reconnect `pending`."""

    type: Literal["ack"] = "ack"
    message_id: int


class PongFrame(BaseModel):
    """The daemon's reply to the hub's ping (heartbeat). Proves the connection is
    alive; 2 cycles without any frame ⇒ the hub drops the zombie connection."""

    type: Literal["pong"] = "pong"


ClientFrame = Annotated[
    HelloFrame | SendMessageFrame | AckFrame | PongFrame, Field(discriminator="type")
]
client_frame_adapter: TypeAdapter[ClientFrame] = TypeAdapter(ClientFrame)

# ---------- hub → client ----------


class GroupInfo(BaseModel):
    slug: str
    display_name: str
    members: list[str]


class HelloAckFrame(BaseModel):
    type: Literal["hello_ack"] = "hello_ack"
    agent_id: str | None  # None for panel connections (observer)
    online: list[str]
    settings: AgentSettings | None  # None for observers
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
    """Returned to the sender after an @group/@all fan-out."""

    type: Literal["broadcast_result"] = "broadcast_result"
    group: str
    sent: list[str]
    skipped: list[str]  # blocked by the recipient's allowlist
    offline: list[str]  # will receive it as pending on reconnect


class ErrorFrame(BaseModel):
    type: Literal["error"] = "error"
    code: str
    detail: str


class PingFrame(BaseModel):
    """The hub's heartbeat. The daemon replies `pong` immediately."""

    type: Literal["ping"] = "ping"


ServerFrame = (
    HelloAckFrame
    | MessageDeliveryFrame
    | DeliveredFrame
    | PresenceFrame
    | SettingsUpdateFrame
    | BroadcastResultFrame
    | ErrorFrame
    | PingFrame
)
