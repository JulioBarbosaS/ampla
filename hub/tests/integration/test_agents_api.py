from tests.helpers import auth, create_agent, create_key, do_setup, register_member


class TestAgentCrud:
    def test_cria_lista_e_consulta(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio", "Backend do Julio")

        agents = client.get("/api/agents", headers=auth(token)).json()
        assert [a["slug"] for a in agents] == ["backend-julio"]
        assert agents[0]["mode"] == "inbox"  # default seguro

        one = client.get("/api/agents/backend-julio", headers=auth(token))
        assert one.status_code == 200

    def test_slug_duplicado_409(self, client):
        admin_token = do_setup(client)
        member_token = register_member(client, admin_token)
        create_agent(client, admin_token, "backend-julio")
        response = client.post(
            "/api/agents",
            json={"slug": "backend-julio", "display_name": "Clone"},
            headers=auth(member_token),
        )
        assert response.status_code == 409

    def test_slug_invalido_422(self, client):
        token = do_setup(client)
        response = client.post(
            "/api/agents",
            json={"slug": "Backend Julio", "display_name": "X"},
            headers=auth(token),
        )
        assert response.status_code == 422

    def test_directory_visivel_a_todos_logados(self, client):
        admin_token = do_setup(client)
        member_token = register_member(client, admin_token)
        create_agent(client, admin_token, "backend-julio")
        directory = client.get("/api/agents/directory", headers=auth(member_token)).json()
        assert directory == [
            {"slug": "backend-julio", "display_name": "backend-julio", "online": False}
        ]


class TestSettings:
    def test_dono_atualiza(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        response = client.patch(
            "/api/agents/backend-julio/settings",
            json={
                "mode": "auto",
                "allowed_senders": ["mobile-eduardo"],
                "instructions": "Só responda sobre o repo backend.",
            },
            headers=auth(token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "auto"
        assert body["allowed_senders"] == ["mobile-eduardo"]

    def test_terceiro_nao_atualiza_403(self, client):
        admin_token = do_setup(client)
        member_token = register_member(client, admin_token)
        create_agent(client, member_token, "mobile-eduardo")
        # admin PODE (gestão), mas outro member não — criamos um segundo member
        second = register_member(
            client,
            admin_token,
            {"email": "joao@example.com", "name": "João", "password": "senha-do-joao-123"},
        )
        response = client.patch(
            "/api/agents/mobile-eduardo/settings",
            json={"mode": "auto"},
            headers=auth(second),
        )
        assert response.status_code == 403

    def test_admin_atualiza_agente_de_member(self, client):
        admin_token = do_setup(client)
        member_token = register_member(client, admin_token)
        create_agent(client, member_token, "mobile-eduardo")
        response = client.patch(
            "/api/agents/mobile-eduardo/settings",
            json={"mode": "auto"},
            headers=auth(admin_token),
        )
        assert response.status_code == 200


class TestKeys:
    def test_cria_chave_plaintext_so_uma_vez(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        key = create_key(client, token, "backend-julio")
        assert key.startswith("amp_")

        listed = client.get("/api/agents/backend-julio/keys", headers=auth(token)).json()
        assert len(listed) == 1
        assert "key" not in listed[0]  # plaintext nunca aparece de novo
        assert listed[0]["revoked_at"] is None

    def test_revoga_chave(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_key(client, token, "backend-julio")
        key_id = client.get("/api/agents/backend-julio/keys", headers=auth(token)).json()[0]["id"]
        response = client.delete(f"/api/agents/backend-julio/keys/{key_id}", headers=auth(token))
        assert response.status_code == 200
        assert response.json()["revoked_at"] is not None

    def test_terceiro_nao_gerencia_chaves(self, client):
        admin_token = do_setup(client)
        member_token = register_member(client, admin_token)
        create_agent(client, admin_token, "backend-julio")
        second = register_member(
            client,
            admin_token,
            {"email": "joao@example.com", "name": "João", "password": "senha-do-joao-123"},
        )
        response = client.post("/api/agents/backend-julio/keys", json={}, headers=auth(second))
        assert response.status_code == 403
        assert member_token  # silencia lint de variável
