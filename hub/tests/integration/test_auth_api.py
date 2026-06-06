from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings
from tests.helpers import ADMIN, MEMBER, auth, do_setup, register_member


class TestSetupFlow:
    def test_fluxo_completo_setup_login_me(self, client):
        assert client.get("/api/auth/setup-status").json() == {"needs_setup": True}

        token = do_setup(client)
        assert client.get("/api/auth/setup-status").json() == {"needs_setup": False}

        me = client.get("/api/auth/me", headers=auth(token))
        assert me.status_code == 200
        assert me.json()["role"] == "admin"
        assert me.json()["email"] == ADMIN["email"]

    def test_setup_segunda_vez_409(self, client):
        do_setup(client)
        response = client.post("/api/auth/setup", json=MEMBER)
        assert response.status_code == 409

    def test_senha_curta_rejeitada(self, client):
        response = client.post(
            "/api/auth/setup",
            json={"email": "a@b.c", "name": "A", "password": "curta"},
        )
        assert response.status_code == 422


class TestRegister:
    def test_registro_por_convite(self, client):
        admin_token = do_setup(client)
        member_token = register_member(client, admin_token)
        me = client.get("/api/auth/me", headers=auth(member_token))
        assert me.json()["role"] == "member"

    def test_convite_invalido_403(self, client):
        do_setup(client)
        body = dict(MEMBER, invite_code="AMP-FAKE-FAKE-FAKE-FAKE")
        assert client.post("/api/auth/register", json=body).status_code == 403

    def test_member_nao_gera_convite(self, client):
        admin_token = do_setup(client)
        member_token = register_member(client, admin_token)
        assert client.post("/api/invites", headers=auth(member_token)).status_code == 403


class TestLogin:
    def test_login_ok(self, client):
        do_setup(client)
        response = client.post(
            "/api/auth/login", json={"email": ADMIN["email"], "password": ADMIN["password"]}
        )
        assert response.status_code == 200
        assert response.json()["token"]

    def test_senha_errada_401_generico(self, client):
        do_setup(client)
        response = client.post(
            "/api/auth/login", json={"email": ADMIN["email"], "password": "senha-errada-123"}
        )
        assert response.status_code == 401
        # Mesma mensagem para conta inexistente (anti user-enumeration)
        response2 = client.post(
            "/api/auth/login", json={"email": "ghost@example.com", "password": "x" * 12}
        )
        assert response2.status_code == 401
        assert response.json()["detail"] == response2.json()["detail"]

    def test_sem_token_401(self, client):
        assert client.get("/api/auth/me").status_code == 401


class TestRateLimit:
    def test_429_apos_limite_por_ip(self):
        app = create_app(make_settings(login_rate_per_minute=3))
        with TestClient(app) as client:
            do_setup(client)  # consome 1 do limite
            payload = {"email": "x@y.z", "password": "tanto-faz-12345"}
            client.post("/api/auth/login", json=payload)  # 2
            client.post("/api/auth/login", json=payload)  # 3
            response = client.post("/api/auth/login", json=payload)  # 4 → bloqueia
            assert response.status_code == 429
