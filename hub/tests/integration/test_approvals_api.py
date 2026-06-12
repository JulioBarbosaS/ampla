"""Human-in-the-loop approvals (Epic 03 · 3.3, slice A2a): the daemon requests
approval over the WS, the hub persists it under the AUTHENTICATED agent and
notifies the owner; owner/admin read the pending list."""

from tests.helpers import (
    auth,
    connect_agent_ws,
    create_agent,
    create_key,
    do_setup,
    recv_until,
    register_member,
)


def _request_approval(client, slug, key, *, to, draft, trigger=None, extra=None):
    """Sends an approval_request on the daemon WS, then flushes via a deliberately
    invalid frame: the sequential receive loop guarantees the prior frame was
    committed once `bad_frame` comes back."""
    frame = {
        "type": "approval_request",
        "trigger_message_id": trigger,
        "to": to,
        "draft_body": draft,
    }
    if extra:
        frame.update(extra)
    with connect_agent_ws(client, slug, key) as ws:
        recv_until(ws, "hello_ack")
        ws.send_json(frame)
        ws.send_json({"type": "message"})  # missing to/body → bad_frame
        assert recv_until(ws, "error")["code"] == "bad_frame"


class TestApprovalRequest:
    def test_request_persists_and_notifies_owner(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        key = create_key(client, token, "backend-julio")
        _request_approval(
            client,
            "backend-julio",
            key,
            to="mobile-eduardo",
            draft="Sim: POST /api/v1/auth/password-reset",
            trigger=42,
        )

        approvals = client.get(
            "/api/agents/backend-julio/approvals?status=pending", headers=auth(token)
        ).json()
        assert len(approvals) == 1
        a = approvals[0]
        assert a["agent_slug"] == "backend-julio"  # attributed to the socket
        assert a["to_agent"] == "mobile-eduardo"
        assert a["status"] == "pending"
        assert a["trigger_message_id"] == 42
        assert a["draft_body"].endswith("password-reset")
        assert a["decided_by"] is None

        # the owner gets an approval_requested notification (always-deliver reason)
        notifs = client.get(
            "/api/notifications?reason=approval_requested", headers=auth(token)
        ).json()
        assert len(notifs) == 1
        assert notifs[0]["agent_slug"] == "backend-julio"
        assert notifs[0]["subject_key"] == f"approval:{a['id']}"

    def test_request_carries_no_agent_id_so_it_cannot_be_spoofed(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        key = create_key(client, token, "backend-julio")
        # a sneaked agent_id is ignored — the row lands under the authenticated slug
        _request_approval(
            client,
            "backend-julio",
            key,
            to="mobile-eduardo",
            draft="oi",
            extra={"agent_id": "mobile-eduardo"},
        )
        mine = client.get("/api/agents/backend-julio/approvals", headers=auth(token)).json()
        other = client.get("/api/agents/mobile-eduardo/approvals", headers=auth(token)).json()
        assert len(mine) == 1
        assert other == []

    def test_non_owner_cannot_list_approvals(self, client):
        admin = do_setup(client)
        member = register_member(client, admin)
        create_agent(client, admin, "backend-julio")
        key = create_key(client, admin, "backend-julio")
        _request_approval(client, "backend-julio", key, to="mobile-eduardo", draft="oi")
        resp = client.get("/api/agents/backend-julio/approvals", headers=auth(member))
        assert resp.status_code == 403
