"""Agent board actions over the WS (Epic 06 · 6.4): a `kanban_action` frame is
attributed to the AUTHENTICATED socket slug (anti-spoof) and gated by the
agent's per-board capability (§6.3) — the hub re-checks, never trusting the
daemon. A dev-only board (default_agent_role=none) rejects every agent mutation."""

from tests.helpers import (
    auth,
    connect_agent_ws,
    create_agent,
    create_key,
    do_setup,
    recv_until,
)


def _board(client, token, **body):
    body.setdefault("name", "Board")
    return client.post("/api/kanban/boards", json=body, headers=auth(token)).json()


def _grant(client, token, board_id, slug, role):
    resp = client.put(
        f"/api/kanban/boards/{board_id}/grants",
        json={"agent_slug": slug, "role": role},
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text


def _cards(client, token, board_id):
    return client.get(f"/api/kanban/boards/{board_id}/full", headers=auth(token)).json()["cards"]


class TestAgentAction:
    def test_contributor_grant_lets_an_agent_create_a_card(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-ana")
        key = create_key(client, token, "backend-ana")
        board = _board(client, token)
        _grant(client, token, board["id"], "backend-ana", "contributor")

        with connect_agent_ws(client, "backend-ana", key) as ws:
            recv_until(ws, "hello_ack")
            ws.send_json(
                {
                    "type": "kanban_action",
                    "board_id": board["id"],
                    "op": "create_card",
                    "payload": {"title": "Tarefa do agente", "priority": "high"},
                }
            )
            ws.send_json({"type": "message"})  # flush: bad_frame proves the action committed
            assert recv_until(ws, "error")["code"] == "bad_frame"

        cards = _cards(client, token, board["id"])
        assert len(cards) == 1
        assert cards[0]["created_by"] == "backend-ana"  # authenticated slug, not client-claimed
        assert cards[0]["title"] == "Tarefa do agente"

    def test_dev_only_board_rejects_agent_create(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-ana")
        key = create_key(client, token, "backend-ana")
        board = _board(client, token)  # default_agent_role=none → dev-only

        with connect_agent_ws(client, "backend-ana", key) as ws:
            recv_until(ws, "hello_ack")
            ws.send_json(
                {
                    "type": "kanban_action",
                    "board_id": board["id"],
                    "op": "create_card",
                    "payload": {"title": "intruso"},
                }
            )
            assert recv_until(ws, "error")["code"] == "permission_denied"

        assert _cards(client, token, board["id"]) == []

    def test_viewer_can_comment_but_not_create(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-ana")
        key = create_key(client, token, "backend-ana")
        board = _board(client, token)
        _grant(client, token, board["id"], "backend-ana", "viewer")
        card = client.post(
            f"/api/kanban/boards/{board['id']}/cards",
            json={"title": "card do dev"},
            headers=auth(token),
        ).json()

        with connect_agent_ws(client, "backend-ana", key) as ws:
            recv_until(ws, "hello_ack")
            # a comment is allowed for a viewer
            ws.send_json(
                {
                    "type": "kanban_action",
                    "board_id": board["id"],
                    "op": "comment",
                    "payload": {"card_id": card["id"], "body": "Preciso de mais contexto aqui"},
                }
            )
            # creating a card is not
            ws.send_json(
                {
                    "type": "kanban_action",
                    "board_id": board["id"],
                    "op": "create_card",
                    "payload": {"title": "não pode"},
                }
            )
            assert recv_until(ws, "error")["code"] == "permission_denied"

        comments = client.get(
            f"/api/kanban/cards/{card['id']}/comments", headers=auth(token)
        ).json()
        assert [c["author"] for c in comments] == ["backend-ana"]
        assert len(_cards(client, token, board["id"])) == 1  # no card added by the agent
