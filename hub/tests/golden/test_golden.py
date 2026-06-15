"""Golden tests — the hub's external contract compared against approved files.

Any contract change (REST or WS protocol) breaks these tests:
if the change is intentional, regenerate the goldens and review the diff in the commit:

    AMP_UPDATE_GOLDEN=1 pytest tests/golden

The ws_frames.json file is also consumed by the bridge's golden test
(bridge/tests/golden/protocol-mirror.test.ts) — it is what LOCKS the
mirroring required in docs/ARCHITECTURE.md · WebSocket protocol.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from app.schemas.agent import AgentSettings
from app.schemas.message import MessageOut
from app.schemas.notification import NotificationOut
from app.schemas.ws import (
    AgentActivityFrame,
    BroadcastResultFrame,
    DeliveredFrame,
    ErrorFrame,
    GroupInfo,
    HelloAckFrame,
    HelloFrame,
    KillSwitchFrame,
    MessageDeliveryFrame,
    NotificationFrame,
    NotificationReadFrame,
    PingFrame,
    PresenceFrame,
    SettingsUpdateFrame,
)

GOLDEN_DIR = Path(__file__).parent


def _accepted_client_frame(raw: dict) -> dict:
    """Ensures the hub accepts the raw frame before freezing it into the golden."""
    from app.schemas.ws import client_frame_adapter

    client_frame_adapter.validate_json(json.dumps(raw))
    return raw


def check_golden(name: str, actual: object) -> None:
    path = GOLDEN_DIR / name
    rendered = json.dumps(actual, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if os.environ.get("AMP_UPDATE_GOLDEN") == "1":
        path.write_text(rendered)
    assert path.exists(), "golden ausente — gere com: AMP_UPDATE_GOLDEN=1 pytest tests/golden"
    assert rendered == path.read_text(), (
        f"contrato divergiu de {name} — se a mudança é intencional, "
        "regenere com AMP_UPDATE_GOLDEN=1 e revise o diff no commit"
    )


def test_openapi_contract(client) -> None:
    """Full REST contract (routes, schemas, status codes)."""
    schema = client.get("/openapi.json").json()
    check_golden("openapi.json", schema)


def test_ws_frames_contract() -> None:
    """WS frames exactly as they travel — mirrored by the bridge."""
    settings = AgentSettings()
    message = MessageOut(
        id=1,
        from_agent="mobile-eduardo",
        to_agent="backend-julio",
        body="Existe endpoint de reset de senha?",
        type="request",
        priority="normal",
        thread_id=1,
        in_reply_to=None,
        created_at=datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC),
        delivered_at=None,
        expires_at=datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC),
    )
    frames = {
        # exclude_none: the daemon sends hello WITHOUT the jwt field (and the panel without key)
        "client.hello": HelloFrame(agent_id="backend-julio", key="amp_" + "ab" * 32).model_dump(
            mode="json", exclude_none=True
        ),
        # minimal frame, as the daemon sends it without options (defaults applied at the hub)
        "client.message": _accepted_client_frame(
            {"type": "message", "to": "backend-julio", "body": "Existe endpoint de reset de senha?"}
        ),
        # full frame, with threading and priority
        "client.message_full": _accepted_client_frame(
            {
                "type": "message",
                "to": "backend-julio",
                "body": "Sim: POST /api/v1/auth/password-reset",
                "msg_type": "response",
                "priority": "high",
                "in_reply_to": 1,
            }
        ),
        "client.broadcast": _accepted_client_frame(
            {"type": "message", "to": "@frontend-team", "body": "deploy às 18h"}
        ),
        # delivery ack (at-least-once) — the daemon confirms receipt
        "client.ack": _accepted_client_frame({"type": "ack", "message_id": 1}),
        # heartbeat: the hub pings, the daemon replies pong
        "client.pong": _accepted_client_frame({"type": "pong"}),
        # auto-respond 'responding…' signal for the panel indicator
        "client.activity": _accepted_client_frame({"type": "activity", "state": "responding"}),
        # auto-respond transcript record (Epic 03 · 3.1) — no agent_id (anti-spoof)
        "client.autorespond_report": _accepted_client_frame(
            {
                "type": "autorespond_report",
                "record": {
                    "trigger_message_id": 1,
                    "from_sender": "mobile-eduardo",
                    "result": "replied",
                    "reason": None,
                    "reply_preview": "Sim: POST /api/v1/auth/password-reset",
                    "tools_allowed": "Read,Grep,Glob",
                    "tools_disallowed": "Bash,NotebookEdit,WebFetch,WebSearch,Edit,Write",
                    "guardrails": {
                        "allow_write": False,
                        "block_hidden_files": True,
                        "block_sensitive_paths": True,
                        "confine_to_dir": True,
                        "trusted_sender": False,
                        "sandbox": "host",
                    },
                    "duration_ms": 1234,
                    "timed_out": False,
                    "input_tokens": None,
                    "output_tokens": None,
                    "cost_usd": None,
                },
            }
        ),
        # human-in-the-loop approval request (Epic 03 · 3.3) — no agent_id (anti-spoof)
        "client.approval_request": _accepted_client_frame(
            {
                "type": "approval_request",
                "trigger_message_id": 1,
                "to": "mobile-eduardo",
                "draft_body": "Sim: POST /api/v1/auth/password-reset",
            }
        ),
        "client.delegate": _accepted_client_frame(
            {
                "type": "delegate",
                "to": "mobile-eduardo",
                "task": "Revisar o fluxo de login",
                "context": "ver auth.py",
            }
        ),
        "server.hello_ack": HelloAckFrame(
            agent_id="backend-julio",
            online=["backend-julio", "mobile-eduardo"],
            settings=settings,
            pending=[message],
            groups=[
                GroupInfo(
                    slug="frontend-team",
                    display_name="Time Frontend",
                    members=["frontend-joao", "mobile-eduardo"],
                )
            ],
        ).model_dump(mode="json", by_alias=True),
        "server.broadcast_result": BroadcastResultFrame(
            group="@frontend-team",
            sent=["frontend-joao", "mobile-eduardo"],
            skipped=[],
            offline=["frontend-joao"],
        ).model_dump(mode="json"),
        "server.message": MessageDeliveryFrame(message=message).model_dump(
            mode="json", by_alias=True
        ),
        "server.delivered": DeliveredFrame(message_id=1, to="backend-julio").model_dump(
            mode="json"
        ),
        "server.presence": PresenceFrame(agent_id="infra-maria", status="offline").model_dump(
            mode="json"
        ),
        "server.agent_activity": AgentActivityFrame(
            agent_id="backend-julio", state="responding"
        ).model_dump(mode="json"),
        "server.settings_update": SettingsUpdateFrame(settings=settings).model_dump(mode="json"),
        "server.error": ErrorFrame(
            code="rate_limited", detail="Limite de mensagens excedido."
        ).model_dump(mode="json"),
        "server.ping": PingFrame().model_dump(mode="json"),
        # global kill switch flip, broadcast to every daemon + observer
        "server.kill_switch": KillSwitchFrame(auto_responder_enabled=False).model_dump(mode="json"),
        # inbox deltas (Epic 02 · slice b) — pushed to the owning user's observers
        "server.notification": NotificationFrame(
            notification=NotificationOut(
                id=1,
                subject_type="dm",
                subject_key="dm:backend-julio:mobile-eduardo",
                agent_slug="backend-julio",
                reason="direct_message",
                title="mobile-eduardo enviou uma mensagem para backend-julio",
                link="/?perspective=backend-julio&partner=mobile-eduardo&msg=1",
                actor="mobile-eduardo",
                unread=True,
                status="inbox",
                created_at=datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC),
                updated_at=datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC),
                last_read_at=None,
            )
        ).model_dump(mode="json"),
        "server.notification_read": NotificationReadFrame(ids=[1, 2], unread_count=3).model_dump(
            mode="json"
        ),
    }
    check_golden("ws_frames.json", frames)
