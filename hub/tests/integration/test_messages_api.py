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
            # At-least-once: the REST send pushes in real time but `delivered_at`
            # stays null until the recipient acks (same contract as the WS path);
            # marking on push would lose the message if the daemon dies first. The
            # ack→delivered flow itself is covered by the WS integration tests.
            assert response.json()["delivered_at"] is None

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


class TestBroadcastAuthz:
    def test_spoofed_broadcast_is_denied_without_consuming_the_owner_bucket(self, client):
        """A user can't exhaust another agent's broadcast bucket by naming it:
        ownership is checked BEFORE the per-agent rate limiter (cap 5/min). A
        storm of spoof attempts must all 403 (never 429) and leave the real
        owner's budget intact."""
        admin = do_setup(client)
        member = register_member(client, admin)
        create_agent(client, admin, "admin-bot")
        create_agent(client, member, "member-bot")  # gives @all a recipient

        # Member spoofs the admin's agent 6× (> the cap of 5). With authz first,
        # every attempt is 403 — the limiter is never touched. (Pre-fix, the 6th
        # would be 429 and the bucket would be full.)
        for _ in range(6):
            resp = client.post(
                "/api/messages/broadcast",
                json={"from": "admin-bot", "group": "@all", "body": "spoof"},
                headers=auth(member),
            )
            assert resp.status_code == 403, resp.text

        # The real owner can still broadcast — its bucket wasn't consumed.
        ok = client.post(
            "/api/messages/broadcast",
            json={"from": "admin-bot", "group": "@all", "body": "real"},
            headers=auth(admin),
        )
        assert ok.status_code == 201, ok.text
