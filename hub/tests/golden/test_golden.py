"""Golden tests — o contrato externo do hub comparado com arquivos aprovados.

Qualquer mudança de contrato (REST ou protocolo WS) quebra estes testes:
se a mudança for intencional, regenere os goldens e revise o diff no commit:

    AMP_UPDATE_GOLDEN=1 pytest tests/golden

O arquivo ws_frames.json também é consumido pelo golden test do bridge
(bridge/tests/golden/protocol-mirror.test.ts) — é o que TRAVA o
espelhamento exigido em docs/ARCHITECTURE.md · Protocolo WebSocket.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from app.schemas.agent import AgentSettings
from app.schemas.message import MessageOut
from app.schemas.ws import (
    BroadcastResultFrame,
    DeliveredFrame,
    ErrorFrame,
    GroupInfo,
    HelloAckFrame,
    HelloFrame,
    MessageDeliveryFrame,
    PresenceFrame,
    SettingsUpdateFrame,
)

GOLDEN_DIR = Path(__file__).parent


def _accepted_client_frame(raw: dict) -> dict:
    """Garante que o hub aceita o frame cru antes de congelá-lo no golden."""
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
    """Contrato REST completo (rotas, schemas, status codes)."""
    schema = client.get("/openapi.json").json()
    check_golden("openapi.json", schema)


def test_ws_frames_contract() -> None:
    """Frames WS exatamente como trafegam — espelhado pelo bridge."""
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
        # exclude_none: o daemon envia hello SEM o campo jwt (e o painel sem key)
        "client.hello": HelloFrame(agent_id="backend-julio", key="amp_" + "ab" * 32).model_dump(
            mode="json", exclude_none=True
        ),
        # frame mínimo, como o daemon envia sem opções (defaults aplicados no hub)
        "client.message": _accepted_client_frame(
            {"type": "message", "to": "backend-julio", "body": "Existe endpoint de reset de senha?"}
        ),
        # frame completo, com threading e prioridade
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
        "server.settings_update": SettingsUpdateFrame(settings=settings).model_dump(mode="json"),
        "server.error": ErrorFrame(
            code="rate_limited", detail="Limite de mensagens excedido."
        ).model_dump(mode="json"),
    }
    check_golden("ws_frames.json", frames)
