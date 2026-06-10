from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings
from tests.helpers import ADMIN, MEMBER, auth, do_setup, register_member


class TestSetupFlow:
    def test_full_setup_login_me_flow(self, client):
        assert client.get("/api/auth/setup-status").json() == {"needs_setup": True}

        token = do_setup(client)
        assert client.get("/api/auth/setup-status").json() == {"needs_setup": False}

        me = client.get("/api/auth/me", headers=auth(token))
        assert me.status_code == 200
        assert me.json()["role"] == "admin"
        assert me.json()["email"] == ADMIN["email"]

    def test_setup_second_time_409(self, client):
        do_setup(client)
        response = client.post("/api/auth/setup", json=MEMBER)
        assert response.status_code == 409

    def test_short_password_rejected(self, client):
        response = client.post(
            "/api/auth/setup",
            json={"email": "a@b.c", "name": "A", "password": "curta"},
        )
        assert response.status_code == 422


class TestProfile:
    def test_patch_me_updates_name(self, client):
        token = do_setup(client)
        response = client.patch("/api/auth/me", json={"name": "Novo Nome"}, headers=auth(token))
        assert response.status_code == 200
        assert response.json()["name"] == "Novo Nome"
        # persisted across requests
        assert client.get("/api/auth/me", headers=auth(token)).json()["name"] == "Novo Nome"

    def test_patch_me_requires_auth(self, client):
        # no setup → no session cookie/token; the dependency must reject it
        assert client.patch("/api/auth/me", json={"name": "x"}).status_code == 401

    def test_patch_me_rejects_empty_name(self, client):
        token = do_setup(client)
        response = client.patch("/api/auth/me", json={"name": ""}, headers=auth(token))
        assert response.status_code == 422


class TestRegister:
    def test_registration_by_invite(self, client):
        admin_token = do_setup(client)
        member_token = register_member(client, admin_token)
        me = client.get("/api/auth/me", headers=auth(member_token))
        assert me.json()["role"] == "member"

    def test_invalid_invite_403(self, client):
        do_setup(client)
        body = dict(MEMBER, invite_code="AMP-FAKE-FAKE-FAKE-FAKE")
        assert client.post("/api/auth/register", json=body).status_code == 403

    def test_member_does_not_generate_invite(self, client):
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

    def test_wrong_password_401_generic(self, client):
        do_setup(client)
        response = client.post(
            "/api/auth/login", json={"email": ADMIN["email"], "password": "senha-errada-123"}
        )
        assert response.status_code == 401
        # Same message for a nonexistent account (anti user-enumeration)
        response2 = client.post(
            "/api/auth/login", json={"email": "ghost@example.com", "password": "x" * 12}
        )
        assert response2.status_code == 401
        assert response.json()["detail"] == response2.json()["detail"]

    def test_without_token_401(self, client):
        assert client.get("/api/auth/me").status_code == 401


class TestRateLimit:
    def test_429_after_per_ip_limit(self):
        app = create_app(make_settings(login_rate_per_minute=3))
        with TestClient(app) as client:
            do_setup(client)  # consumes 1 of the limit
            payload = {"email": "x@y.z", "password": "tanto-faz-12345"}
            client.post("/api/auth/login", json=payload)  # 2
            client.post("/api/auth/login", json=payload)  # 3
            response = client.post("/api/auth/login", json=payload)  # 4 → blocks
            assert response.status_code == 429
