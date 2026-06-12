"""User inbox (Epic 02 · slice a): generation from sends, the read endpoints,
and strict per-user isolation."""

from tests.helpers import auth, create_agent, do_setup, recv_until, register_member


def _send(client, token, frm, to, body):
    resp = client.post(
        "/api/messages", json={"from": frm, "to": to, "body": body}, headers=auth(token)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestGeneration:
    def test_dm_generates_a_notification_for_the_recipient_owner(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        _send(client, token, "mobile-eduardo", "backend-julio", "tem reset de senha?")

        items = client.get("/api/notifications", headers=auth(token)).json()
        assert len(items) == 1
        n = items[0]
        assert n["reason"] == "direct_message"
        assert n["agent_slug"] == "backend-julio"
        assert n["actor"] == "mobile-eduardo"
        assert n["unread"] is True
        assert n["status"] == "inbox"
        assert "backend-julio" in n["link"]  # hub-built deep link, no agent text

        count = client.get("/api/notifications/unread-count", headers=auth(token)).json()
        assert count == {"unread_count": 1}

    def test_repeated_dm_collapses_into_one_thread(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        _send(client, token, "mobile-eduardo", "backend-julio", "primeira")
        _send(client, token, "mobile-eduardo", "backend-julio", "segunda")
        items = client.get("/api/notifications", headers=auth(token)).json()
        assert len(items) == 1  # collapsed onto the same thread

    def test_mention_notifies_the_mentioned_owner_only(self, client):
        admin = do_setup(client)
        member = register_member(client, admin)
        create_agent(client, admin, "backend-julio")  # admin's
        create_agent(client, member, "mobile-eduardo")  # member's
        create_agent(client, member, "frontend-ze")  # member's (recipient)

        _send(client, member, "mobile-eduardo", "frontend-ze", "ei @backend-julio, dá uma olhada")

        # admin (owner of the mentioned agent) gets a mention
        admin_items = client.get("/api/notifications", headers=auth(admin)).json()
        assert [n["reason"] for n in admin_items] == ["mention"]
        assert admin_items[0]["agent_slug"] == "backend-julio"

        # member (recipient's owner) gets the DM, but NOT the mention
        member_items = client.get("/api/notifications", headers=auth(member)).json()
        assert [n["reason"] for n in member_items] == ["direct_message"]


class TestTriageAndIsolation:
    def test_mark_read_and_set_status(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        _send(client, token, "mobile-eduardo", "backend-julio", "oi")
        nid = client.get("/api/notifications", headers=auth(token)).json()[0]["id"]

        read = client.patch(
            f"/api/notifications/{nid}", json={"unread": False}, headers=auth(token)
        ).json()
        assert read["unread"] is False
        assert read["last_read_at"] is not None
        assert client.get("/api/notifications/unread-count", headers=auth(token)).json() == {
            "unread_count": 0
        }

        done = client.patch(
            f"/api/notifications/{nid}", json={"status": "done"}, headers=auth(token)
        ).json()
        assert done["status"] == "done"
        # the inbox view no longer lists it
        inbox = client.get("/api/notifications?status=inbox", headers=auth(token)).json()
        assert inbox == []

    def test_observer_receives_notification_then_read_deltas(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        # panel observer (rides the session cookie set by do_setup)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "hello"})
            recv_until(ws, "hello_ack")

            _send(client, token, "mobile-eduardo", "backend-julio", "oi")
            frame = recv_until(ws, "notification")
            assert frame["notification"]["reason"] == "direct_message"
            nid = frame["notification"]["id"]

            # triage in this "tab" → a read delta syncs others (badge + ids)
            client.patch(f"/api/notifications/{nid}", json={"unread": False}, headers=auth(token))
            read = recv_until(ws, "notification_read")
            assert read["ids"] == [nid]
            assert read["unread_count"] == 0

    def test_read_all_clears_unread_and_pushes_an_all_delta(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        create_agent(client, token, "frontend-ze")
        _send(client, token, "mobile-eduardo", "backend-julio", "um")
        _send(client, token, "frontend-ze", "backend-julio", "dois")
        assert client.get("/api/notifications/unread-count", headers=auth(token)).json() == {
            "unread_count": 2
        }
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "hello"})
            recv_until(ws, "hello_ack")
            resp = client.post("/api/notifications/read-all", headers=auth(token))
            assert resp.json() == {"unread_count": 0}
            delta = recv_until(ws, "notification_read")
            assert delta["ids"] == "all"
            assert delta["unread_count"] == 0
        assert client.get("/api/notifications/unread-count", headers=auth(token)).json() == {
            "unread_count": 0
        }

    def test_read_all_only_touches_own(self, client):
        admin = do_setup(client)
        member = register_member(client, admin)
        create_agent(client, admin, "backend-julio")
        create_agent(client, admin, "mobile-eduardo")
        create_agent(client, member, "frontend-ze")
        create_agent(client, member, "infra-ana")
        _send(client, admin, "mobile-eduardo", "backend-julio", "p/ admin")
        _send(client, member, "infra-ana", "frontend-ze", "p/ member")
        # admin clears only their own inbox
        client.post("/api/notifications/read-all", headers=auth(admin))
        assert client.get("/api/notifications/unread-count", headers=auth(admin)).json() == {
            "unread_count": 0
        }
        assert client.get("/api/notifications/unread-count", headers=auth(member)).json() == {
            "unread_count": 1
        }

    def test_cross_user_patch_is_404(self, client):
        admin = do_setup(client)
        member = register_member(client, admin)
        create_agent(client, admin, "backend-julio")
        create_agent(client, admin, "mobile-eduardo")
        _send(client, admin, "mobile-eduardo", "backend-julio", "oi")
        nid = client.get("/api/notifications", headers=auth(admin)).json()[0]["id"]
        # member cannot touch (or even confirm the existence of) admin's notification
        resp = client.patch(
            f"/api/notifications/{nid}", json={"unread": False}, headers=auth(member)
        )
        assert resp.status_code == 404
