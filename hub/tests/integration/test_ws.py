"""Integração do canal WebSocket: autenticação, roteamento, pendentes,
allowlist, settings_update, presença e observers."""

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings
from tests.helpers import (
    auth,
    connect_agent_ws,
    create_agent,
    create_key,
    do_setup,
    recv_until,
)


def setup_two_agents(client) -> tuple[str, str, str]:
    """admin com backend-julio e mobile-eduardo. Retorna (token, key_a, key_b)."""
    token = do_setup(client)
    create_agent(client, token, "backend-julio")
    create_agent(client, token, "mobile-eduardo")
    return (
        token,
        create_key(client, token, "backend-julio"),
        create_key(client, token, "mobile-eduardo"),
    )


class TestAuth:
    def test_chave_invalida_recebe_error(self, client):
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

    def test_hello_incompleto_recebe_error(self, client):
        do_setup(client)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "hello"})
            assert ws.receive_json()["code"] == "bad_hello"

    def test_hello_valido_recebe_ack_com_settings(self, client):
        token, key_a, _ = setup_two_agents(client)
        with connect_agent_ws(client, "backend-julio", key_a) as ws:
            ack = recv_until(ws, "hello_ack")
            assert ack["agent_id"] == "backend-julio"
            assert "backend-julio" in ack["online"]
            assert ack["settings"]["mode"] == "inbox"
            assert ack["pending"] == []


class TestRouting:
    def test_mensagem_roteada_em_tempo_real(self, client):
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

                delivered = recv_until(ws_b, "delivered")
                assert delivered["to"] == "backend-julio"

    def test_historico_via_rest_apos_ws(self, client):
        token, key_a, key_b = setup_two_agents(client)
        with connect_agent_ws(client, "backend-julio", key_a) as ws_a:
            recv_until(ws_a, "hello_ack")
            with connect_agent_ws(client, "mobile-eduardo", key_b) as ws_b:
                recv_until(ws_b, "hello_ack")
                ws_b.send_json({"type": "message", "to": "backend-julio", "body": "oi"})
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

    def test_destinatario_offline_recebe_no_proximo_hello(self, client):
        _, key_a, key_b = setup_two_agents(client)
        with connect_agent_ws(client, "mobile-eduardo", key_b) as ws_b:
            recv_until(ws_b, "hello_ack")
            ws_b.send_json({"type": "message", "to": "backend-julio", "body": "está aí?"})
            # destinatário offline ⇒ sem frame delivered
            ws_b.send_json({"type": "message", "to": "backend-julio", "body": "segunda"})
            # barreira: frames são processados em ordem — o error do destino
            # inexistente garante que as duas anteriores foram persistidas
            ws_b.send_json({"type": "message", "to": "fantasma-x", "body": "sync"})
            assert recv_until(ws_b, "error")["code"] == "not_found"

        with connect_agent_ws(client, "backend-julio", key_a) as ws_a:
            ack = recv_until(ws_a, "hello_ack")
            bodies = [m["body"] for m in ack["pending"]]
            assert bodies == ["está aí?", "segunda"]  # ordem de chegada
            # barreira: garante que o flush de delivered completou antes
            # de fechar (handler processa frames em ordem)
            ws_a.send_json({"type": "message", "to": "fantasma-x", "body": "sync"})
            recv_until(ws_a, "error")

        # flush marca como entregue: reconectar não repete
        with connect_agent_ws(client, "backend-julio", key_a) as ws_a:
            assert recv_until(ws_a, "hello_ack")["pending"] == []

    def test_threading_e_type_via_ws(self, client):
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

    def test_destinatario_inexistente_gera_error(self, client):
        _, key_a, _ = setup_two_agents(client)
        with connect_agent_ws(client, "backend-julio", key_a) as ws:
            recv_until(ws, "hello_ack")
            ws.send_json({"type": "message", "to": "fantasma-x", "body": "eco"})
            assert recv_until(ws, "error")["code"] == "not_found"


class TestBroadcastWs:
    def test_fan_out_em_tempo_real_com_offline_e_result(self, client):
        token, key_a, key_b = setup_two_agents(client)
        create_agent(client, token, "infra-maria")  # ficará offline
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

    def test_rate_limit_de_broadcast(self):
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

    def test_grupo_inexistente_gera_error(self, client):
        _, key_a, _ = setup_two_agents(client)
        with connect_agent_ws(client, "backend-julio", key_a) as ws:
            recv_until(ws, "hello_ack")
            ws.send_json({"type": "message", "to": "@fantasmas", "body": "eco"})
            assert recv_until(ws, "error")["code"] == "not_found"


class TestAllowlist:
    def test_hub_bloqueia_remetente_fora_da_allowlist(self, client):
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
    def test_patch_no_painel_empurra_settings_update(self, client):
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
    def test_revogar_chave_derruba_websocket(self, client):
        token, key_a, _ = setup_two_agents(client)
        key_id = client.get("/api/agents/backend-julio/keys", headers=auth(token)).json()[0]["id"]
        with connect_agent_ws(client, "backend-julio", key_a) as ws:
            recv_until(ws, "hello_ack")
            client.delete(f"/api/agents/backend-julio/keys/{key_id}", headers=auth(token))
            # a conexão deve cair — qualquer recv subsequente termina em disconnect
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
    def test_painel_observa_mensagens_e_presenca(self, client):
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

    def test_jwt_invalido_nao_observa(self, client):
        do_setup(client)
        with client.websocket_connect("/ws") as observer:
            observer.send_json({"type": "hello", "jwt": "forjado"})
            assert observer.receive_json()["code"] == "auth_failed"


class TestAbuse:
    def test_rate_limit_por_conexao(self):
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

    def test_frames_malformados_derrubam_conexao(self, client):
        import pytest
        from starlette.websockets import WebSocketDisconnect

        _, key_a, _ = setup_two_agents(client)
        with connect_agent_ws(client, "backend-julio", key_a) as ws:
            recv_until(ws, "hello_ack")
            with pytest.raises(WebSocketDisconnect):
                for _ in range(10):
                    ws.send_text("não é json")
                    ws.receive_json()  # consome os error frames até cair
