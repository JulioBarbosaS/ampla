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

    def test_change_password_flow(self, client):
        token = do_setup(client)
        response = client.post(
            "/api/auth/me/password",
            json={"current_password": ADMIN["password"], "new_password": "outra-senha-segura-9"},
            headers=auth(token),
        )
        assert response.status_code == 204
        # the old password no longer logs in; the new one does
        old = client.post(
            "/api/auth/login", json={"email": ADMIN["email"], "password": ADMIN["password"]}
        )
        assert old.status_code == 401
        new = client.post(
            "/api/auth/login",
            json={"email": ADMIN["email"], "password": "outra-senha-segura-9"},
        )
        assert new.status_code == 200

    def test_change_password_wrong_current_is_422_not_401(self, client):
        token = do_setup(client)
        response = client.post(
            "/api/auth/me/password",
            json={"current_password": "senha-errada-9", "new_password": "outra-senha-segura-9"},
            headers=auth(token),
        )
        # 422, not 401 — a wrong current password must not look like a dead session
        assert response.status_code == 422

    def test_change_password_requires_auth(self, client):
        response = client.post(
            "/api/auth/me/password",
            json={"current_password": "x", "new_password": "y" * 12},
        )
        assert response.status_code == 401


def _png_data_url() -> str:
    import base64
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (12, 12), (200, 100, 50)).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class TestAvatar:
    def test_upload_serve_and_delete(self, client):
        token = do_setup(client)
        uid = client.get("/api/auth/me", headers=auth(token)).json()["id"]

        # no avatar yet → 404 (client falls back to the initial)
        assert client.get(f"/api/users/{uid}/avatar", headers=auth(token)).status_code == 404

        up = client.post(
            "/api/auth/me/avatar", json={"image": _png_data_url()}, headers=auth(token)
        )
        assert up.status_code == 204

        got = client.get(f"/api/users/{uid}/avatar", headers=auth(token))
        assert got.status_code == 200
        # always re-encoded to JPEG server-side, never the original PNG bytes
        assert got.headers["content-type"] == "image/jpeg"
        assert got.headers["x-content-type-options"] == "nosniff"
        assert got.content[:2] == b"\xff\xd8"  # JPEG magic

        assert client.delete("/api/auth/me/avatar", headers=auth(token)).status_code == 204
        assert client.get(f"/api/users/{uid}/avatar", headers=auth(token)).status_code == 404

    def test_rejects_a_non_image(self, client):
        token = do_setup(client)
        import base64

        junk = "data:image/png;base64," + base64.b64encode(b"not an image").decode()
        response = client.post("/api/auth/me/avatar", json={"image": junk}, headers=auth(token))
        assert response.status_code == 422

    def test_upload_requires_auth(self, client):
        assert client.post("/api/auth/me/avatar", json={"image": "x"}).status_code == 401


class TestPasswordReset:
    def test_admin_issues_and_user_resets(self, client):
        admin_token = do_setup(client)
        member_token = register_member(client, admin_token)
        member_id = client.get("/api/auth/me", headers=auth(member_token)).json()["id"]

        issued = client.post(
            f"/api/users/{member_id}/password-reset", headers=auth(admin_token)
        )
        assert issued.status_code == 200
        token = issued.json()["token"]

        reset = client.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": "senha-redefinida-1"},
        )
        assert reset.status_code == 204
        # the member logs in with the new password
        login = client.post(
            "/api/auth/login", json={"email": MEMBER["email"], "password": "senha-redefinida-1"}
        )
        assert login.status_code == 200

    def test_member_cannot_issue_reset(self, client):
        admin_token = do_setup(client)
        member_token = register_member(client, admin_token)
        member_id = client.get("/api/auth/me", headers=auth(member_token)).json()["id"]
        assert (
            client.post(
                f"/api/users/{member_id}/password-reset", headers=auth(member_token)
            ).status_code
            == 403
        )

    def test_invalid_reset_token_is_422(self, client):
        do_setup(client)
        response = client.post(
            "/api/auth/reset-password",
            json={"token": "token-invalido-aqui", "new_password": "senha-redefinida-1"},
        )
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
