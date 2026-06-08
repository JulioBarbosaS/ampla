"""User management (admin): list and promote/demote roles."""

from tests.helpers import auth, do_setup, register_member


class TestUsersApi:
    def test_admin_lists_users(self, client):
        admin_token = do_setup(client)
        register_member(client, admin_token)
        users = client.get("/api/users", headers=auth(admin_token)).json()
        assert {u["role"] for u in users} == {"admin", "member"}

    def test_member_does_not_list(self, client):
        admin_token = do_setup(client)
        member_token = register_member(client, admin_token)
        assert client.get("/api/users", headers=auth(member_token)).status_code == 403

    def test_admin_promotes_member(self, client):
        admin_token = do_setup(client)
        register_member(client, admin_token)
        users = client.get("/api/users", headers=auth(admin_token)).json()
        member_id = next(u["id"] for u in users if u["role"] == "member")
        response = client.patch(
            f"/api/users/{member_id}/role", json={"role": "admin"}, headers=auth(admin_token)
        )
        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    def test_does_not_demote_last_admin(self, client):
        admin_token = do_setup(client)
        me = client.get("/api/auth/me", headers=auth(admin_token)).json()
        response = client.patch(
            f"/api/users/{me['id']}/role", json={"role": "member"}, headers=auth(admin_token)
        )
        assert response.status_code == 409

    def test_member_does_not_change_role(self, client):
        admin_token = do_setup(client)
        member_token = register_member(client, admin_token)
        me = client.get("/api/auth/me", headers=auth(admin_token)).json()
        response = client.patch(
            f"/api/users/{me['id']}/role", json={"role": "member"}, headers=auth(member_token)
        )
        assert response.status_code == 403
