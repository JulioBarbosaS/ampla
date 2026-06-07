"""Grupos e broadcast via REST: CRUD, governança e fan-out."""

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
    def test_cria_lista_e_remove(self, client):
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

    def test_slug_all_reservado_422(self, client):
        admin_token, _ = setup_team(client)
        response = client.post(
            "/api/groups",
            json={"slug": "all", "display_name": "Todos"},
            headers=auth(admin_token),
        )
        assert response.status_code == 422

    def test_colisao_grupo_agente_409_nos_dois_sentidos(self, client):
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
    def test_dono_adiciona_terceiro_nao(self, client):
        admin_token, member_token = setup_team(client)
        client.post(
            "/api/groups",
            json={"slug": "mobile-team", "display_name": "M"},
            headers=auth(admin_token),
        )
        # member adiciona o PRÓPRIO agente: ok
        response = client.post(
            "/api/groups/mobile-team/members",
            json={"agent": "mobile-eduardo"},
            headers=auth(member_token),
        )
        assert response.status_code == 204
        # member tenta adicionar agente do admin: 403
        response = client.post(
            "/api/groups/mobile-team/members",
            json={"agent": "backend-julio"},
            headers=auth(member_token),
        )
        assert response.status_code == 403


class TestBroadcastRest:
    def test_fan_out_via_painel(self, client):
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

        # cada destinatário vê a mensagem na conversa, marcada com o grupo
        history = client.get(
            "/api/messages/conversation",
            params={"a": "backend-julio", "b": "mobile-eduardo"},
            headers=auth(member_token),
        ).json()
        assert history[0]["body"] == "deploy às 18h"
        assert history[0]["group"] == "@all"

    def test_nao_envia_broadcast_por_agente_alheio(self, client):
        _, member_token = setup_team(client)
        response = client.post(
            "/api/messages/broadcast",
            json={"from": "backend-julio", "group": "@all", "body": "falso"},
            headers=auth(member_token),
        )
        assert response.status_code == 403
