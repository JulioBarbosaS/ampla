"""WebSocket channel integration: authentication, routing, pending,
allowlist, settings_update, presence and observers."""

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings
from tests.helpers import (
    ack,
    auth,
    connect_agent_ws,
    create_agent,
    create_key,
    do_setup,
    recv_until,
)


def setup_two_agents(client) -> tuple[str, str, str]:
    """admin with backend-julio and mobile-eduardo. Returns (token, key_a, key_b)."""
    token = do_setup(client)
    create_agent(client, token, "backend-julio")
    create_agent(client, token, "mobile-eduardo")
    return (
        token,
        create_key(client, token, "backend-julio"),
        create_key(client, token, "mobile-eduardo"),
    )


class TestAuth:
    def test_invalid_key_receives_error(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "hello", "agent_id": "backend-julio", "key": "amp_falsa"})
            frame = ws.receive_json()
            assert frame == {
                "type": "error",
                "code": "auth_failed",
                "detail": "Chave inválida ou revogada.",
            }

    def test_incomplete_hello_receives_error(self, client):
        do_setup(client)
        client.cookies.clear()  # no session cookie either → genuinely credential-less
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "hello"})
            assert ws.receive_json()["code"] == "bad_hello"

    def test_valid_hello_receives_ack_with_settings(self, client):
        token, key_a, _ = setup_two_agents(client)
        with connect_agent_ws(client, "backend-julio", key_a) as ws:
            ack = recv_until(ws, "hello_ack")
            assert ack["agent_id"] == "backend-julio"
            assert "backend-julio" in ack["online"]
            assert ack["settings"]["mode"] == "inbox"
            assert ack["pending"] == []


class TestRouting:
    def test_message_routed_in_real_time(self, client):
        _, key_a, key_b = setup_two_agents(client)
        with connect_agent_ws(client, "backend-julio", key_a) as ws_a:
            recv_until(ws_a, "hello_ack")
            with connect_agent_ws(client, "mobile-eduardo", key_b) as ws_b:
                recv_until(ws_b, "hello_ack")

                ws_b.send_json(
                    {"type": "message", "to": "backend-julio", "body": "Existe endpoint de reset?"}
                )
                received = recv_until(ws_a, "message")
                assert received["message"]["from"] == "mobile-eduardo"
                assert received["message"]["body"] == "Existe endpoint de reset?"
                # at-least-once: on dispatch the message is NOT confirmed yet
                assert received["message"]["delivered_at"] is None

                # the sender only receives `delivered` after the recipient acks
                ack(ws_a, received["message"]["id"])
                delivered = recv_until(ws_b, "delivered")
                assert delivered["to"] == "backend-julio"
                assert delivered["message_id"] == received["message"]["id"]

    def test_history_via_rest_after_ws(self, client):
        token, key_a, key_b = setup_two_agents(client)
        with connect_agent_ws(client, "backend-julio", key_a) as ws_a:
            recv_until(ws_a, "hello_ack")
            with connect_agent_ws(client, "mobile-eduardo", key_b) as ws_b:
                recv_until(ws_b, "hello_ack")
                ws_b.send_json({"type": "message", "to": "backend-julio", "body": "oi"})
                # recipient confirms → delivered_at is written to the database
                ack(ws_a, recv_until(ws_a, "message")["message"]["id"])
                recv_until(ws_b, "delivered")

        history = client.get(
            "/api/messages/conversation",
            params={"a": "backend-julio", "b": "mobile-eduardo"},
            headers=auth(token),
        ).json()
        assert len(history) == 1
        assert history[0]["delivered_at"] is not None

        partners = client.get(
            "/api/messages/partners",
            params={"agent": "backend-julio"},
            headers=auth(token),
        ).json()
        assert partners[0]["agent"] == "mobile-eduardo"

    def test_offline_recipient_receives_on_next_hello(self, client):
        _, key_a, key_b = setup_two_agents(client)
        with connect_agent_ws(client, "mobile-eduardo", key_b) as ws_b:
            recv_until(ws_b, "hello_ack")
            ws_b.send_json({"type": "message", "to": "backend-julio", "body": "está aí?"})
            # recipient offline ⇒ no delivered frame
            ws_b.send_json({"type": "message", "to": "backend-julio", "body": "segunda"})
            # barrier: frames are processed in order — the error from the
            # nonexistent destination guarantees the previous two were persisted
            ws_b.send_json({"type": "message", "to": "fantasma-x", "body": "sync"})
            assert recv_until(ws_b, "error")["code"] == "not_found"

        with connect_agent_ws(client, "backend-julio", key_a) as ws_a:
            hello = recv_until(ws_a, "hello_ack")
            pending = hello["pending"]
            assert [m["body"] for m in pending] == ["está aí?", "segunda"]  # arrival order
            # confirm each pending one (at-least-once) — without an ack they would return
            for m in pending:
                ack(ws_a, m["id"])
            # barrier: the handler processes frames in order, so the error guarantees
            # the previous acks were already processed before closing
            ws_a.send_json({"type": "message", "to": "fantasma-x", "body": "sync"})
            recv_until(ws_a, "error")

        # acks marked them as delivered: reconnecting does not repeat them
        with connect_agent_ws(client, "backend-julio", key_a) as ws_a:
            assert recv_until(ws_a, "hello_ack")["pending"] == []

    def test_without_ack_the_message_returns_in_pending(self, client):
        """The fix itself: a message pushed to the socket but NOT acked (the daemon
        crashed before storing it) returns in the reconnect pending — no silent loss.
        Before, the hub marked delivered on dispatch and it vanished."""
        _, key_a, key_b = setup_two_agents(client)
        with connect_agent_ws(client, "mobile-eduardo", key_b) as ws_b:
            recv_until(ws_b, "hello_ack")
            with connect_agent_ws(client, "backend-julio", key_a) as ws_a:
                recv_until(ws_a, "hello_ack")
                ws_b.send_json({"type": "message", "to": "backend-julio", "body": "não ackada"})
                received = recv_until(ws_a, "message")["message"]
                assert received["delivered_at"] is None  # not confirmed yet
                # backend drops WITHOUT acking (exits the with block)

        with connect_agent_ws(client, "backend-julio", key_a) as ws_a:
            pending = recv_until(ws_a, "hello_ack")["pending"]
            assert [m["body"] for m in pending] == ["não ackada"]

    def test_threading_and_type_via_ws(self, client):
        _, key_a, key_b = setup_two_agents(client)
        with connect_agent_ws(client, "backend-julio", key_a) as ws_a:
            recv_until(ws_a, "hello_ack")
            with connect_agent_ws(client, "mobile-eduardo", key_b) as ws_b:
                recv_until(ws_b, "hello_ack")

                ws_b.send_json({"type": "message", "to": "backend-julio", "body": "pergunta?"})
                root = recv_until(ws_a, "message")["message"]
                assert root["type"] == "request"
                assert root["thread_id"] == root["id"]

                ws_a.send_json(
                    {
                        "type": "message",
                        "to": "mobile-eduardo",
                        "body": "resposta!",
                        "msg_type": "response",
                        "priority": "high",
                        "in_reply_to": root["id"],
                    }
                )
                reply = recv_until(ws_b, "message")["message"]
                assert reply["type"] == "response"
                assert reply["priority"] == "high"
                assert reply["thread_id"] == root["id"]
                assert reply["in_reply_to"] == root["id"]

    def test_nonexistent_recipient_raises_error(self, client):
        _, key_a, _ = setup_two_agents(client)
        with connect_agent_ws(client, "backend-julio", key_a) as ws:
            recv_until(ws, "hello_ack")
            ws.send_json({"type": "message", "to": "fantasma-x", "body": "eco"})
            assert recv_until(ws, "error")["code"] == "not_found"


class TestBroadcastWs:
    def test_fan_out_in_real_time_with_offline_and_result(self, client):
        token, key_a, key_b = setup_two_agents(client)
        create_agent(client, token, "infra-maria")  # will stay offline
        client.post(
            "/api/groups",
            json={"slug": "equipe", "display_name": "Equipe"},
            headers=auth(token),
        )
        for agent in ("backend-julio", "mobile-eduardo", "infra-maria"):
            client.post("/api/groups/equipe/members", json={"agent": agent}, headers=auth(token))

        with connect_agent_ws(client, "backend-julio", key_a) as ws_a:
            ack = recv_until(ws_a, "hello_ack")
            assert ack["groups"] == [
                {
                    "slug": "equipe",
                    "display_name": "Equipe",
                    "members": ["backend-julio", "infra-maria", "mobile-eduardo"],
                }
            ]
            with connect_agent_ws(client, "mobile-eduardo", key_b) as ws_b:
                recv_until(ws_b, "hello_ack")

                ws_a.send_json({"type": "message", "to": "@equipe", "body": "standup agora?"})
                received = recv_until(ws_b, "message")["message"]
                assert received["group"] == "@equipe"
                assert received["from"] == "backend-julio"

                result = recv_until(ws_a, "broadcast_result")
                assert sorted(result["sent"]) == ["infra-maria", "mobile-eduardo"]
                assert result["offline"] == ["infra-maria"]
                assert result["skipped"] == []

    def test_broadcast_rate_limit(self):
        app = create_app(make_settings(broadcast_per_minute=2))
        with TestClient(app) as client:
            _, key_a, _ = setup_two_agents(client)
            with connect_agent_ws(client, "backend-julio", key_a) as ws:
                recv_until(ws, "hello_ack")
                for _ in range(2):
                    ws.send_json({"type": "message", "to": "@all", "body": "spam?"})
                    recv_until(ws, "broadcast_result")
                ws.send_json({"type": "message", "to": "@all", "body": "bloqueia"})
                assert recv_until(ws, "error")["code"] == "rate_limited"

    def test_nonexistent_group_raises_error(self, client):
        _, key_a, _ = setup_two_agents(client)
        with connect_agent_ws(client, "backend-julio", key_a) as ws:
            recv_until(ws, "hello_ack")
            ws.send_json({"type": "message", "to": "@fantasmas", "body": "eco"})
            assert recv_until(ws, "error")["code"] == "not_found"


class TestAllowlist:
    def test_hub_blocks_sender_outside_the_allowlist(self, client):
        token, key_a, key_b = setup_two_agents(client)
        client.patch(
            "/api/agents/backend-julio/settings",
            json={"allowed_senders": ["frontend-joao"]},
            headers=auth(token),
        )
        with connect_agent_ws(client, "backend-julio", key_a) as ws_a:
            recv_until(ws_a, "hello_ack")
            with connect_agent_ws(client, "mobile-eduardo", key_b) as ws_b:
                recv_until(ws_b, "hello_ack")
                ws_b.send_json({"type": "message", "to": "backend-julio", "body": "oi"})
                assert recv_until(ws_b, "error")["code"] == "permission_denied"


class TestSettingsPush:
    def test_panel_patch_pushes_settings_update(self, client):
        token, key_a, _ = setup_two_agents(client)
        with connect_agent_ws(client, "backend-julio", key_a) as ws:
            recv_until(ws, "hello_ack")
            client.patch(
                "/api/agents/backend-julio/settings",
                json={"mode": "auto", "max_auto_per_hour": 3},
                headers=auth(token),
            )
            update = recv_until(ws, "settings_update")
            assert update["settings"]["mode"] == "auto"
            assert update["settings"]["max_auto_per_hour"] == 3


class TestRevocation:
    def test_revoking_key_broadcasts_offline(self, client):
        """Bug: a revoked agent stayed 'online' forever (ghost presence)."""
        token, key_a, key_b = setup_two_agents(client)
        key_id = client.get("/api/agents/mobile-eduardo/keys", headers=auth(token)).json()[0]["id"]
        with connect_agent_ws(client, "backend-julio", key_a) as ws_a:
            recv_until(ws_a, "hello_ack")
            with connect_agent_ws(client, "mobile-eduardo", key_b) as ws_b:
                recv_until(ws_b, "hello_ack")
                recv_until(ws_a, "presence")  # mobile comes online
                client.delete(f"/api/agents/mobile-eduardo/keys/{key_id}", headers=auth(token))
                frame = recv_until(ws_a, "presence")
                assert frame == {
                    "type": "presence",
                    "agent_id": "mobile-eduardo",
                    "status": "offline",
                }

    def test_revoking_key_drops_websocket(self, client):
        token, key_a, _ = setup_two_agents(client)
        key_id = client.get("/api/agents/backend-julio/keys", headers=auth(token)).json()[0]["id"]
        with connect_agent_ws(client, "backend-julio", key_a) as ws:
            recv_until(ws, "hello_ack")
            client.delete(f"/api/agents/backend-julio/keys/{key_id}", headers=auth(token))
            # the connection should drop — any subsequent recv ends in a disconnect
            import pytest
            from starlette.websockets import WebSocketDisconnect

            with pytest.raises(WebSocketDisconnect):
                while True:
                    ws.receive_json()


class TestPresence:
    def test_broadcast_online_offline(self, client):
        _, key_a, key_b = setup_two_agents(client)
        with connect_agent_ws(client, "backend-julio", key_a) as ws_a:
            recv_until(ws_a, "hello_ack")
            with connect_agent_ws(client, "mobile-eduardo", key_b) as ws_b:
                recv_until(ws_b, "hello_ack")
                frame = recv_until(ws_a, "presence")
                assert frame == {
                    "type": "presence",
                    "agent_id": "mobile-eduardo",
                    "status": "online",
                }
            frame = recv_until(ws_a, "presence")
            assert frame["agent_id"] == "mobile-eduardo"
            assert frame["status"] == "offline"


class TestObserver:
    def test_panel_observes_messages_and_presence(self, client):
        token, key_a, key_b = setup_two_agents(client)
        with client.websocket_connect("/ws") as observer:
            observer.send_json({"type": "hello", "jwt": token})
            ack = recv_until(observer, "hello_ack")
            assert ack["agent_id"] is None

            with connect_agent_ws(client, "backend-julio", key_a) as ws_a:
                recv_until(ws_a, "hello_ack")
                assert recv_until(observer, "presence")["agent_id"] == "backend-julio"

                with connect_agent_ws(client, "mobile-eduardo", key_b) as ws_b:
                    recv_until(ws_b, "hello_ack")
                    ws_b.send_json({"type": "message", "to": "backend-julio", "body": "olá"})
                    mirrored = recv_until(observer, "message")
                    assert mirrored["message"]["from"] == "mobile-eduardo"

    def test_invalid_jwt_does_not_observe(self, client):
        do_setup(client)
        with client.websocket_connect("/ws") as observer:
            observer.send_json({"type": "hello", "jwt": "forjado"})
            assert observer.receive_json()["code"] == "auth_failed"


class TestAbuse:
    def test_rate_limit_per_connection(self):
        app = create_app(
            make_settings(ws_messages_per_minute=4)  # burst = max(4//4, 5) = 5
        )
        with TestClient(app) as client:
            _, key_a, key_b = setup_two_agents(client)
            with connect_agent_ws(client, "mobile-eduardo", key_b) as ws:
                recv_until(ws, "hello_ack")
                got_limited = False
                for i in range(8):
                    ws.send_json({"type": "message", "to": "backend-julio", "body": f"m{i}"})
                for _ in range(20):
                    frame = ws.receive_json()
                    if frame["type"] == "error" and frame["code"] == "rate_limited":
                        got_limited = True
                        break
                assert got_limited

    def test_malformed_frames_drop_connection(self, client):
        import pytest
        from starlette.websockets import WebSocketDisconnect

        _, key_a, _ = setup_two_agents(client)
        with connect_agent_ws(client, "backend-julio", key_a) as ws:
            recv_until(ws, "hello_ack")
            with pytest.raises(WebSocketDisconnect):
                for _ in range(10):
                    ws.send_text("não é json")
                    ws.receive_json()  # consume the error frames until it drops


class TestHeartbeat:
    def test_hub_sends_ping(self):
        app = create_app(make_settings(ws_heartbeat_secs=0.2))
        with TestClient(app) as client:
            _, key_a, _ = setup_two_agents(client)
            with connect_agent_ws(client, "backend-julio", key_a) as ws:
                recv_until(ws, "hello_ack")
                assert recv_until(ws, "ping")["type"] == "ping"

    def test_without_pong_the_connection_is_dropped(self):
        import pytest
        from starlette.websockets import WebSocketDisconnect

        app = create_app(make_settings(ws_heartbeat_secs=0.1))
        with TestClient(app) as client:
            _, key_a, _ = setup_two_agents(client)
            with connect_agent_ws(client, "backend-julio", key_a) as ws:
                recv_until(ws, "hello_ack")
                # never replies pong → 2 cycles without a frame ⇒ the hub closes
                with pytest.raises(WebSocketDisconnect):
                    for _ in range(50):
                        ws.receive_json()

    def test_pong_keeps_the_connection_alive(self):
        app = create_app(make_settings(ws_heartbeat_secs=0.1))
        with TestClient(app) as client:
            _, key_a, _ = setup_two_agents(client)
            with connect_agent_ws(client, "backend-julio", key_a) as ws:
                recv_until(ws, "hello_ack")
                # replies to the pings: the connection survives beyond 2 cycles
                for _ in range(3):
                    recv_until(ws, "ping")
                    ws.send_json({"type": "pong"})
                # still alive: a normal send is routed (nonexistent destination)
                ws.send_json({"type": "message", "to": "fantasma-x", "body": "vivo?"})
                assert recv_until(ws, "error")["code"] == "not_found"
