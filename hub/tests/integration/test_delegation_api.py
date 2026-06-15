"""Agent-to-agent delegation over the WS (Epic 04 · 4.4): a delegate frame
creates a delegations row + a task message to the delegate, attributed to the
AUTHENTICATED socket, and owner/admin read the delegations via REST."""

from tests.helpers import (
    auth,
    connect_agent_ws,
    create_agent,
    create_key,
    do_setup,
    recv_until,
    register_member,
)


def _delegate(client, slug: str, key: str, frame: dict) -> None:
    """Sends a delegate frame, then flushes with a deliberately invalid frame: the
    bad_frame error coming back proves the delegation was already committed."""
    with connect_agent_ws(client, slug, key) as ws:
        recv_until(ws, "hello_ack")
        ws.send_json({"type": "delegate", **frame})
        ws.send_json({"type": "message"})  # missing to/body → bad_frame
        assert recv_until(ws, "error")["code"] == "bad_frame"


class TestDelegate:
    def test_delegate_creates_open_delegation(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        key = create_key(client, token, "backend-julio")
        _delegate(
            client,
            "backend-julio",
            key,
            {"to": "mobile-eduardo", "task": "Revisar o fluxo de login", "context": "ver auth.py"},
        )

        rows = client.get("/api/agents/backend-julio/delegations", headers=auth(token)).json()
        assert len(rows) == 1
        assert rows[0]["from_agent"] == "backend-julio"  # authenticated socket
        assert rows[0]["to_agent"] == "mobile-eduardo"
        assert rows[0]["status"] == "open"
        assert rows[0]["root_message_id"] is not None

        # the delegate also shows it as received (involved either side)
        as_delegate = client.get(
            "/api/agents/mobile-eduardo/delegations", headers=auth(token)
        ).json()
        assert len(as_delegate) == 1

    def test_self_delegation_is_rejected(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        key = create_key(client, token, "backend-julio")
        with connect_agent_ws(client, "backend-julio", key) as ws:
            recv_until(ws, "hello_ack")
            ws.send_json({"type": "delegate", "to": "backend-julio", "task": "x", "context": ""})
            assert recv_until(ws, "error")["code"] == "invalid_input"

        rows = client.get("/api/agents/backend-julio/delegations", headers=auth(token)).json()
        assert rows == []

    def test_completes_when_the_delegate_replies_in_thread(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        a_key = create_key(client, token, "backend-julio")
        b_key = create_key(client, token, "mobile-eduardo")

        # A delegates to B (flush so the task message is persisted before B connects)
        _delegate(client, "backend-julio", a_key, {"to": "mobile-eduardo", "task": "tarefa"})

        # B connects, gets the task as pending, and replies in-thread → completes
        with connect_agent_ws(client, "mobile-eduardo", b_key) as ws_b:
            ack = recv_until(ws_b, "hello_ack")
            pending = ack["pending"]
            assert len(pending) == 1 and pending[0]["type"] == "task"
            task_id = pending[0]["id"]
            ws_b.send_json(
                {
                    "type": "message",
                    "to": "backend-julio",
                    "body": "feito",
                    "msg_type": "response",
                    "in_reply_to": task_id,
                }
            )
            ws_b.send_json({"type": "message"})  # flush: bad_frame proves the reply committed
            assert recv_until(ws_b, "error")["code"] == "bad_frame"

        rows = client.get("/api/agents/backend-julio/delegations", headers=auth(token)).json()
        assert rows[0]["status"] == "completed"
        assert rows[0]["result_message_id"] is not None

    def test_non_owner_cannot_list_delegations(self, client):
        admin = do_setup(client)
        member = register_member(client, admin)
        create_agent(client, admin, "backend-julio")
        resp = client.get("/api/agents/backend-julio/delegations", headers=auth(member))
        assert resp.status_code == 403
