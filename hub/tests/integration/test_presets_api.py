"""Guardrail presets endpoints (Epic 04 · 4.1): built-ins seeded at startup,
CRUD, and apply copies settings onto the agent + pushes to the daemon."""

from tests.helpers import auth, create_agent, do_setup, register_member


class TestPresets:
    def test_builtins_are_seeded_and_listed(self, client):
        token = do_setup(client)
        presets = client.get("/api/guardrail-presets", headers=auth(token)).json()
        names = [p["name"] for p in presets]
        assert "Estrito (padrão)" in names
        assert "Confiável (perigo)" in names
        # built-ins carry no owner
        assert all(p["owner_id"] is None for p in presets if p["name"].startswith("Estrito"))

    def test_create_update_delete_personal_preset(self, client):
        token = do_setup(client)
        created = client.post(
            "/api/guardrail-presets",
            json={"name": "Meu preset", "settings": {"mode": "auto", "allow_write": True}},
            headers=auth(token),
        )
        assert created.status_code == 201, created.text
        pid = created.json()["id"]
        assert created.json()["settings"]["allow_write"] is True

        patched = client.patch(
            f"/api/guardrail-presets/{pid}",
            json={"name": "Renomeado"},
            headers=auth(token),
        )
        assert patched.json()["name"] == "Renomeado"

        deleted = client.delete(f"/api/guardrail-presets/{pid}", headers=auth(token))
        assert deleted.status_code == 204

    def test_apply_preset_copies_settings_to_the_agent(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        pid = client.post(
            "/api/guardrail-presets",
            json={
                "name": "Auto+escrita",
                "settings": {"mode": "auto", "allow_write": True, "confine_to_dir": False},
            },
            headers=auth(token),
        ).json()["id"]

        applied = client.post(
            "/api/agents/backend-julio/apply-preset",
            json={"preset_id": pid},
            headers=auth(token),
        )
        assert applied.status_code == 200, applied.text
        agent = applied.json()
        assert agent["mode"] == "auto"
        assert agent["allow_write"] is True
        assert agent["confine_to_dir"] is False

    def test_member_cannot_apply_to_anothers_agent(self, client):
        admin = do_setup(client)
        member = register_member(client, admin)
        create_agent(client, admin, "backend-julio")
        pid = client.post(
            "/api/guardrail-presets",
            json={"name": "X", "settings": {"mode": "inbox"}},
            headers=auth(member),
        ).json()["id"]
        resp = client.post(
            "/api/agents/backend-julio/apply-preset",
            json={"preset_id": pid},
            headers=auth(member),
        )
        assert resp.status_code == 403

    def test_create_rejects_bad_settings(self, client):
        token = do_setup(client)
        resp = client.post(
            "/api/guardrail-presets",
            json={"name": "Ruim", "settings": {"mode": "telepatia"}},
            headers=auth(token),
        )
        assert resp.status_code == 422
