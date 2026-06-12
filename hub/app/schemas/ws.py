"""WebSocket protocol — canonical definition.

MIRROR: bridge/src/shared/protocol.ts. Change it here, change it there IN THE SAME COMMIT
(docs/ARCHITECTURE.md · WebSocket protocol).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from app.schemas.agent import AgentSettings
from app.schemas.message import PRIORITY_PATTERN, TYPE_PATTERN, MessageOut
from app.schemas.notification import NotificationOut

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


class ActivityFrame(BaseModel):
    """The daemon signals that it started (or finished) generating an auto-reply,
    so the panel can show a 'responding…' indicator. Transient — never persisted."""

    type: Literal["activity"] = "activity"
    state: Literal["responding", "idle"]


class AutorespondRecord(BaseModel):
    """One auto-respond run, reported by the daemon (Epic 03 · 3.1). The hub
    stores it as an autorespond_runs row, attributing it to the socket's
    AUTHENTICATED agent — the record carries no agent_id, so a daemon cannot
    claim a run for someone else (anti-spoof, like ack)."""

    trigger_message_id: int | None = None
    from_sender: str = Field(max_length=60)
    result: Literal["replied", "blocked", "failed", "skipped"]
    reason: str | None = Field(default=None, max_length=500)
    # Bounded reply preview (the full reply already lives as a normal message).
    reply_preview: str = Field(default="", max_length=4000)
    tools_allowed: str = Field(default="", max_length=500)
    tools_disallowed: str = Field(default="", max_length=500)
    guardrails: dict = Field(default_factory=dict)
    duration_ms: int = Field(default=0, ge=0)
    timed_out: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


class AutorespondReportFrame(BaseModel):
    """Daemon→hub: an auditable record of one auto-respond run. Sent after each
    run on the authenticated WS (Epic 03 · 3.1)."""

    type: Literal["autorespond_report"] = "autorespond_report"
    record: AutorespondRecord


class ApprovalRequestFrame(BaseModel):
    """Daemon→hub: the auto-responder drafted a reply but the agent has
    require_approval on, so it asks the owner instead of sending (Epic 03 · 3.3).

    No agent_id — the hub attributes it to the socket's AUTHENTICATED agent
    (anti-spoof, like the autorespond report). The draft is already secret-filter
    clean (the daemon scans before drafting); the hub stores it as plain text."""

    type: Literal["approval_request"] = "approval_request"
    trigger_message_id: int | None = None
    to: str = Field(max_length=60)
    draft_body: str = Field(min_length=1, max_length=16384)


ClientFrame = Annotated[
    HelloFrame
    | SendMessageFrame
    | AckFrame
    | PongFrame
    | ActivityFrame
    | AutorespondReportFrame
    | ApprovalRequestFrame,
    Field(discriminator="type"),
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
    # Global kill switch state (Epic 03 · 3.2): the daemon learns it on connect
    # so a reconnect can't resume auto-respond while the switch is engaged.
    auto_responder_enabled: bool = True


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


class AgentActivityFrame(BaseModel):
    """Fan-out to panel observers: an agent started/stopped generating an
    auto-reply (the 'responding…' indicator). Not sent to daemons."""

    type: Literal["agent_activity"] = "agent_activity"
    agent_id: str
    state: Literal["responding", "idle"]


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


class KillSwitchFrame(BaseModel):
    """Hub→all clients: the global kill switch flipped. Broadcast to every daemon
    (which gates auto-respond on it) AND every panel observer (which shows a
    banner) the moment an admin toggles it (Epic 03 · 3.2)."""

    type: Literal["kill_switch"] = "kill_switch"
    auto_responder_enabled: bool


class NotificationFrame(BaseModel):
    """Hub→panel: a new or collapsed inbox notification for THIS user (Epic 02).
    Pushed only to the owning user's observers; daemons ignore it."""

    type: Literal["notification"] = "notification"
    notification: NotificationOut


class NotificationReadFrame(BaseModel):
    """Hub→panel: read-state changed elsewhere (multi-tab/device sync). Carries
    the affected ids (or "all") and the refreshed unread badge count."""

    type: Literal["notification_read"] = "notification_read"
    ids: list[int] | Literal["all"]
    unread_count: int


ServerFrame = (
    HelloAckFrame
    | MessageDeliveryFrame
    | DeliveredFrame
    | PresenceFrame
    | AgentActivityFrame
    | SettingsUpdateFrame
    | BroadcastResultFrame
    | ErrorFrame
    | PingFrame
    | KillSwitchFrame
    | NotificationFrame
    | NotificationReadFrame
)
