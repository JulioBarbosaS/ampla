"""Groups and broadcast via REST: CRUD, governance and fan-out."""

from tests.helpers import auth, create_agent, do_setup, register_member


def setup_team(client) -> tuple[str, str]:
    """admin (backend-julio, infra-julio) + member (mobile-eduardo)."""
    admin_token = do_setup(client)
    member_token = register_member(client, admin_token)
    create_agent(client, admin_token, "backend-julio")
    create_agent(client, admin_token, "infra-julio")
    create_agent(client, member_token, "mobile-eduardo")
    return admin_token, member_token


class TestGroupCrud:
    def test_creates_lists_and_removes(self, client):
        admin_token, _ = setup_team(client)
        response = client.post(
            "/api/groups",
            json={"slug": "backend-team", "display_name": "Time Backend"},
            headers=auth(admin_token),
        )
        assert response.status_code == 201

        groups = client.get("/api/groups", headers=auth(admin_token)).json()
        assert [g["slug"] for g in groups] == ["backend-team"]
        assert groups[0]["members"] == []

        assert (
            client.delete("/api/groups/backend-team", headers=auth(admin_token)).status_code == 204
        )
        assert client.get("/api/groups", headers=auth(admin_token)).json() == []

    def test_slug_all_reserved_422(self, client):
        admin_token, _ = setup_team(client)
        response = client.post(
            "/api/groups",
            json={"slug": "all", "display_name": "Todos"},
            headers=auth(admin_token),
        )
        assert response.status_code == 422

    def test_group_agent_collision_409_both_ways(self, client):
        admin_token, _ = setup_team(client)
        response = client.post(
            "/api/groups",
            json={"slug": "backend-julio", "display_name": "X"},
            headers=auth(admin_token),
        )
        assert response.status_code == 409

        client.post(
            "/api/groups",
            json={"slug": "backend-team", "display_name": "T"},
            headers=auth(admin_token),
        )
        response = client.post(
            "/api/agents",
            json={"slug": "backend-team", "display_name": "Agente Impostor"},
            headers=auth(admin_token),
        )
        assert response.status_code == 409


class TestMembership:
    def test_owner_adds_third_party_does_not(self, client):
        admin_token, member_token = setup_team(client)
        client.post(
            "/api/groups",
            json={"slug": "mobile-team", "display_name": "M"},
            headers=auth(admin_token),
        )
        # member adds their OWN agent: ok
        response = client.post(
            "/api/groups/mobile-team/members",
            json={"agent": "mobile-eduardo"},
            headers=auth(member_token),
        )
        assert response.status_code == 204
        # member tries to add the admin's agent: 403
        response = client.post(
            "/api/groups/mobile-team/members",
            json={"agent": "backend-julio"},
            headers=auth(member_token),
        )
        assert response.status_code == 403


class TestBroadcastRest:
    def test_fan_out_via_panel(self, client):
        admin_token, member_token = setup_team(client)
        response = client.post(
            "/api/messages/broadcast",
            json={"from": "backend-julio", "group": "@all", "body": "deploy às 18h"},
            headers=auth(admin_token),
        )
        assert response.status_code == 201
        result = response.json()
        assert sorted(result["sent"]) == ["infra-julio", "mobile-eduardo"]
        assert result["skipped"] == []

        # each recipient sees the message in the conversation, tagged with the group
        history = client.get(
            "/api/messages/conversation",
            params={"a": "backend-julio", "b": "mobile-eduardo"},
            headers=auth(member_token),
        ).json()
        assert history[0]["body"] == "deploy às 18h"
        assert history[0]["group"] == "@all"

    def test_does_not_send_broadcast_for_someone_elses_agent(self, client):
        _, member_token = setup_team(client)
        response = client.post(
            "/api/messages/broadcast",
            json={"from": "backend-julio", "group": "@all", "body": "falso"},
            headers=auth(member_token),
        )
        assert response.status_code == 403
