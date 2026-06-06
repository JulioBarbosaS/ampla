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
    DeliveredFrame,
    ErrorFrame,
    HelloAckFrame,
    HelloFrame,
    MessageDeliveryFrame,
    PresenceFrame,
    SendMessageFrame,
    SettingsUpdateFrame,
)

GOLDEN_DIR = Path(__file__).parent


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
        created_at=datetime(2026, 6, 6, 12, 0, 0, tzinfo=UTC),
        delivered_at=None,
    )
    frames = {
        # exclude_none: o daemon envia hello SEM o campo jwt (e o painel sem key)
        "client.hello": HelloFrame(agent_id="backend-julio", key="amp_" + "ab" * 32).model_dump(
            mode="json", exclude_none=True
        ),
        "client.message": SendMessageFrame(
            to="backend-julio", body="Existe endpoint de reset de senha?"
        ).model_dump(mode="json"),
        "server.hello_ack": HelloAckFrame(
            agent_id="backend-julio",
            online=["backend-julio", "mobile-eduardo"],
            settings=settings,
            pending=[message],
        ).model_dump(mode="json", by_alias=True),
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
