"""Kanban REST API (Epic 06 · 6.1): board/column/card/comment CRUD end to end,
plus the cross-user authorization convention (invisible board → 404, visible
but non-owner governance → 403)."""

from tests.helpers import auth, create_agent, do_setup, register_member


def _create_board(client, token, **body):
    body.setdefault("name", "Sprint 1")
    resp = client.post("/api/kanban/boards", json=body, headers=auth(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestBoardCrud:
    def test_create_board_seeds_full_payload(self, client):
        token = do_setup(client)
        board = _create_board(client, token)
        full = client.get(f"/api/kanban/boards/{board['id']}/full", headers=auth(token)).json()
        assert full["board"]["name"] == "Sprint 1"
        assert len(full["columns"]) == 5
        assert sum(c["is_landing"] for c in full["columns"]) == 1
        assert full["cards"] == []

    def test_list_boards(self, client):
        token = do_setup(client)
        _create_board(client, token, name="A")
        _create_board(client, token, name="B")
        boards = client.get("/api/kanban/boards", headers=auth(token)).json()
        assert {b["name"] for b in boards} == {"A", "B"}

    def test_update_and_delete_board(self, client):
        token = do_setup(client)
        board = _create_board(client, token)
        patched = client.patch(
            f"/api/kanban/boards/{board['id']}",
            json={"name": "Renomeado", "visibility": "private"},
            headers=auth(token),
        ).json()
        assert patched["name"] == "Renomeado" and patched["visibility"] == "private"
        assert (
            client.delete(f"/api/kanban/boards/{board['id']}", headers=auth(token)).status_code
            == 204
        )
        assert (
            client.get(f"/api/kanban/boards/{board['id']}", headers=auth(token)).status_code == 404
        )


class TestCardsAndComments:
    def test_create_card_and_comment_flow(self, client):
        token = do_setup(client)
        board = _create_board(client, token)
        card = client.post(
            f"/api/kanban/boards/{board['id']}/cards",
            json={"title": "Implementar OAuth", "priority": "high"},
            headers=auth(token),
        )
        assert card.status_code == 201, card.text
        card_id = card.json()["id"]
        assert card.json()["created_by"].startswith("user:")  # authenticated, not client-claimed
        assert card.json()["version"] == 1

        comment = client.post(
            f"/api/kanban/cards/{card_id}/comments",
            json={"body": "Preciso da spec do provider"},
            headers=auth(token),
        )
        assert comment.status_code == 201, comment.text
        comments = client.get(f"/api/kanban/cards/{card_id}/comments", headers=auth(token)).json()
        assert [c["body"] for c in comments] == ["Preciso da spec do provider"]

    def test_stale_version_update_is_409(self, client):
        token = do_setup(client)
        board = _create_board(client, token)
        card_id = client.post(
            f"/api/kanban/boards/{board['id']}/cards",
            json={"title": "x"},
            headers=auth(token),
        ).json()["id"]
        # first edit bumps version 1 → 2
        client.patch(f"/api/kanban/cards/{card_id}", json={"title": "y"}, headers=auth(token))
        # a client still holding version 1 is rejected
        stale = client.patch(
            f"/api/kanban/cards/{card_id}",
            json={"title": "z", "expected_version": 1},
            headers=auth(token),
        )
        assert stale.status_code == 409, stale.text

    def test_column_crud(self, client):
        token = do_setup(client)
        board = _create_board(client, token)
        col = client.post(
            f"/api/kanban/boards/{board['id']}/columns",
            json={"name": "Bloqueado", "wip_limit": 2},
            headers=auth(token),
        )
        assert col.status_code == 201, col.text
        col_id = col.json()["id"]
        assert col.json()["wip_limit"] == 2
        # empty + non-landing → deletable
        assert (
            client.delete(
                f"/api/kanban/boards/{board['id']}/columns/{col_id}", headers=auth(token)
            ).status_code
            == 204
        )


class TestMove:
    def _three_cards(self, client, token, board_id):
        return [
            client.post(
                f"/api/kanban/boards/{board_id}/cards",
                json={"title": t},
                headers=auth(token),
            ).json()
            for t in ("a", "b", "c")
        ]

    def test_move_reorders_and_persists(self, client):
        token = do_setup(client)
        board = _create_board(client, token)
        a, b, c = self._three_cards(client, token, board["id"])
        # move c between a and b
        resp = client.post(
            f"/api/kanban/cards/{c['id']}/move",
            json={
                "to_column_id": a["column_id"],
                "before_id": a["id"],
                "after_id": b["id"],
                "expected_version": c["version"],
            },
            headers=auth(token),
        )
        assert resp.status_code == 200, resp.text
        full = client.get(f"/api/kanban/boards/{board['id']}/full", headers=auth(token)).json()
        landing = [x for x in full["cards"] if x["column_id"] == a["column_id"]]
        landing.sort(key=lambda x: x["rank"])
        assert [x["id"] for x in landing] == [a["id"], c["id"], b["id"]]

    def test_move_with_stale_version_is_409(self, client):
        token = do_setup(client)
        board = _create_board(client, token)
        a, b, c = self._three_cards(client, token, board["id"])
        # bump c's version with an edit
        client.patch(f"/api/kanban/cards/{c['id']}", json={"title": "c2"}, headers=auth(token))
        resp = client.post(
            f"/api/kanban/cards/{c['id']}/move",
            json={
                "to_column_id": a["column_id"],
                "before_id": a["id"],
                "after_id": b["id"],
                "expected_version": c["version"],  # stale (was 1, now 2)
            },
            headers=auth(token),
        )
        assert resp.status_code == 409, resp.text

    def test_move_into_full_column_is_409(self, client):
        token = do_setup(client)
        board = _create_board(client, token)
        full = client.get(f"/api/kanban/boards/{board['id']}/full", headers=auth(token)).json()
        landing = next(c for c in full["columns"] if c["is_landing"])
        other = next(c for c in full["columns"] if not c["is_landing"])
        client.patch(
            f"/api/kanban/boards/{board['id']}/columns/{landing['id']}",
            json={"wip_limit": 1},
            headers=auth(token),
        )
        # one card already in landing
        client.post(
            f"/api/kanban/boards/{board['id']}/cards", json={"title": "x"}, headers=auth(token)
        )
        intruder = client.post(
            f"/api/kanban/boards/{board['id']}/cards",
            json={"title": "y", "column_id": other["id"]},
            headers=auth(token),
        ).json()
        resp = client.post(
            f"/api/kanban/cards/{intruder['id']}/move",
            json={"to_column_id": landing["id"], "expected_version": intruder["version"]},
            headers=auth(token),
        )
        assert resp.status_code == 409, resp.text


class TestAuthorization:
    def test_private_board_is_404_for_other_user(self, client):
        admin = do_setup(client)
        member = register_member(client, admin)
        board = _create_board(client, admin, visibility="private")
        assert (
            client.get(f"/api/kanban/boards/{board['id']}", headers=auth(member)).status_code == 404
        )

    def test_team_member_cannot_change_governance(self, client):
        admin = do_setup(client)
        member = register_member(client, admin)
        board = _create_board(client, admin, visibility="team")
        # visible
        assert (
            client.get(f"/api/kanban/boards/{board['id']}", headers=auth(member)).status_code == 200
        )
        # but governance is owner-only
        resp = client.patch(
            f"/api/kanban/boards/{board['id']}", json={"name": "hack"}, headers=auth(member)
        )
        assert resp.status_code == 403, resp.text

    def test_team_member_can_add_card(self, client):
        admin = do_setup(client)
        member = register_member(client, admin)
        board = _create_board(client, admin, visibility="team")
        resp = client.post(
            f"/api/kanban/boards/{board['id']}/cards",
            json={"title": "do membro"},
            headers=auth(member),
        )
        assert resp.status_code == 201, resp.text


class TestGrants:
    def test_set_list_remove_grant(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-ana")
        board = _create_board(client, token)
        put = client.put(
            f"/api/kanban/boards/{board['id']}/grants",
            json={"agent_slug": "backend-ana", "role": "contributor"},
            headers=auth(token),
        )
        assert put.status_code == 200, put.text
        assert put.json() == {
            "board_id": board["id"],
            "agent_slug": "backend-ana",
            "role": "contributor",
        }
        grants = client.get(f"/api/kanban/boards/{board['id']}/grants", headers=auth(token)).json()
        assert [g["agent_slug"] for g in grants] == ["backend-ana"]
        # upsert: same agent, new role
        client.put(
            f"/api/kanban/boards/{board['id']}/grants",
            json={"agent_slug": "backend-ana", "role": "editor"},
            headers=auth(token),
        )
        grants = client.get(f"/api/kanban/boards/{board['id']}/grants", headers=auth(token)).json()
        assert grants[0]["role"] == "editor"
        # remove
        assert (
            client.delete(
                f"/api/kanban/boards/{board['id']}/grants/backend-ana", headers=auth(token)
            ).status_code
            == 204
        )
        assert (
            client.get(f"/api/kanban/boards/{board['id']}/grants", headers=auth(token)).json() == []
        )

    def test_grant_unknown_agent_is_404(self, client):
        token = do_setup(client)
        board = _create_board(client, token)
        resp = client.put(
            f"/api/kanban/boards/{board['id']}/grants",
            json={"agent_slug": "ghost-agent", "role": "viewer"},
            headers=auth(token),
        )
        assert resp.status_code == 404, resp.text

    def test_non_owner_cannot_manage_grants(self, client):
        admin = do_setup(client)
        member = register_member(client, admin)
        create_agent(client, admin, "backend-ana")
        board = _create_board(client, admin, visibility="team")
        resp = client.put(
            f"/api/kanban/boards/{board['id']}/grants",
            json={"agent_slug": "backend-ana", "role": "editor"},
            headers=auth(member),
        )
        assert resp.status_code == 403, resp.text
