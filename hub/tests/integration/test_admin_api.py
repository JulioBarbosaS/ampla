"""Admin kill switch: authz, persistence, audit, and the real-time broadcast
to connected daemons (Epic 03 · 3.2)."""

from tests.helpers import (
    auth,
    connect_agent_ws,
    create_agent,
    create_key,
    do_setup,
    recv_until,
    register_member,
)


class TestKillSwitch:
    def test_default_is_enabled(self, client):
        token = do_setup(client)
        body = client.get("/api/admin/kill-switch", headers=auth(token)).json()
        assert body == {"auto_responder_enabled": True}

    def test_requires_authentication(self, client):
        do_setup(client)
        client.cookies.clear()
        assert client.get("/api/admin/kill-switch").status_code == 401
        assert client.post("/api/admin/kill-switch", json={"enabled": False}).status_code == 401

    def test_member_is_forbidden(self, client):
        admin = do_setup(client)
        member = register_member(client, admin)
        assert client.get("/api/admin/kill-switch", headers=auth(member)).status_code == 403
        resp = client.post("/api/admin/kill-switch", json={"enabled": False}, headers=auth(member))
        assert resp.status_code == 403

    def test_toggle_persists_round_trip(self, client):
        token = do_setup(client)
        off = client.post("/api/admin/kill-switch", json={"enabled": False}, headers=auth(token))
        assert off.status_code == 200
        assert off.json() == {"auto_responder_enabled": False}
        # still off on a fresh read (persisted)
        assert client.get("/api/admin/kill-switch", headers=auth(token)).json() == {
            "auto_responder_enabled": False
        }
        on = client.post("/api/admin/kill-switch", json={"enabled": True}, headers=auth(token))
        assert on.json() == {"auto_responder_enabled": True}

    def test_toggle_broadcasts_kill_switch_to_connected_daemon(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        key = create_key(client, token, "backend-julio")
        with connect_agent_ws(client, "backend-julio", key) as ws:
            recv_until(ws, "hello_ack")
            client.post("/api/admin/kill-switch", json={"enabled": False}, headers=auth(token))
            frame = recv_until(ws, "kill_switch")
            assert frame == {"type": "kill_switch", "auto_responder_enabled": False}
