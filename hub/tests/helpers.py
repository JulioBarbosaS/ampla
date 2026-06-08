"""Helpers shared by the integration tests."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from starlette.testclient import WebSocketTestSession

ADMIN = {"email": "admin@example.com", "name": "Admin", "password": "senha-muito-segura-1"}
MEMBER = {"email": "dev@example.com", "name": "Dev", "password": "outra-senha-segura-2"}


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def do_setup(client) -> str:
    """Creates the initial admin and returns the JWT."""
    response = client.post("/api/auth/setup", json=ADMIN)
    assert response.status_code == 200, response.text
    return response.json()["token"]


def register_member(client, admin_token: str, member: dict | None = None) -> str:
    """Admin generates an invite; the member registers. Returns the member's JWT."""
    invite = client.post("/api/invites", headers=auth(admin_token))
    assert invite.status_code == 201, invite.text
    body = dict(member or MEMBER)
    body["invite_code"] = invite.json()["code"]
    response = client.post("/api/auth/register", json=body)
    assert response.status_code == 200, response.text
    return response.json()["token"]


def create_agent(client, token: str, slug: str, display_name: str | None = None) -> dict:
    response = client.post(
        "/api/agents",
        json={"slug": slug, "display_name": display_name or slug},
        headers=auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_key(client, token: str, slug: str) -> str:
    """Creates a key and returns the plaintext (the only time it appears)."""
    response = client.post(f"/api/agents/{slug}/keys", json={}, headers=auth(token))
    assert response.status_code == 201, response.text
    return response.json()["key"]


@contextmanager
def connect_agent_ws(client, slug: str, key: str) -> Iterator[WebSocketTestSession]:
    """Opens the WS and sends the daemon hello. The caller consumes the hello_ack."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "hello", "agent_id": slug, "key": key})
        yield ws


def ack(ws: WebSocketTestSession, message_id: int) -> None:
    """Confirms receipt (at-least-once) — without this the hub does not mark
    delivered nor notify the sender, and the message comes back on the next hello."""
    ws.send_json({"type": "ack", "message_id": message_id})


def recv_until(ws: WebSocketTestSession, frame_type: str, max_frames: int = 20) -> dict[str, Any]:
    """Reads frames, discarding those of other types (e.g. interleaved presence)."""
    for _ in range(max_frames):
        frame = ws.receive_json()
        if frame["type"] == frame_type:
            return frame
    raise AssertionError(f"frame {frame_type!r} não recebido em {max_frames} frames")
