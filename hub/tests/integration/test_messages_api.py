"""POST /api/messages — a human sends on behalf of their own agent (panel)."""

from tests.helpers import (
    auth,
    connect_agent_ws,
    create_agent,
    create_key,
    do_setup,
    recv_until,
    register_member,
)


class TestSendAsUser:
    def test_owner_sends_through_their_own_agent(self, client):
        admin_token = do_setup(client)
        member_token = register_member(client, admin_token)
        create_agent(client, member_token, "mobile-eduardo")
        create_agent(client, admin_token, "backend-julio")

        response = client.post(
            "/api/messages",
            json={"from": "mobile-eduardo", "to": "backend-julio", "body": "via painel"},
            headers=auth(member_token),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["from"] == "mobile-eduardo"
        assert body["delivered_at"] is None  # recipient offline

        history = client.get(
            "/api/messages/conversation",
            params={"a": "mobile-eduardo", "b": "backend-julio"},
            headers=auth(member_token),
        ).json()
        assert [m["body"] for m in history] == ["via painel"]

    def test_does_not_send_through_a_third_partys_agent(self, client):
        admin_token = do_setup(client)
        member_token = register_member(client, admin_token)
        create_agent(client, admin_token, "backend-julio")
        create_agent(client, member_token, "mobile-eduardo")

        response = client.post(
            "/api/messages",
            json={"from": "backend-julio", "to": "mobile-eduardo", "body": "falsificada"},
            headers=auth(member_token),
        )
        assert response.status_code == 403

    def test_real_time_delivery_to_an_online_daemon(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        key = create_key(client, token, "backend-julio")

        with connect_agent_ws(client, "backend-julio", key) as ws:
            recv_until(ws, "hello_ack")
            response = client.post(
                "/api/messages",
                json={"from": "mobile-eduardo", "to": "backend-julio", "body": "olá!"},
                headers=auth(token),
            )
            assert response.status_code == 201
            assert response.json()["delivered_at"] is not None

            frame = recv_until(ws, "message")
            assert frame["message"]["body"] == "olá!"

    def test_allowlist_also_applies_to_panel_sends(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        client.patch(
            "/api/agents/backend-julio/settings",
            json={"allowed_senders": ["frontend-joao"]},
            headers=auth(token),
        )
        response = client.post(
            "/api/messages",
            json={"from": "mobile-eduardo", "to": "backend-julio", "body": "bloqueada"},
            headers=auth(token),
        )
        assert response.status_code == 403
