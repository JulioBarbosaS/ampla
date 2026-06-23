"""Scheduled agent tasks REST API (Epic 08 · 8.3): CRUD end to end, the
ownership rule (you only schedule your own agents), and spec validation."""

from tests.helpers import auth, create_agent, do_setup, register_member


def _create(client, token, slug, **body):
    body.setdefault("name", "Standup diário")
    body.setdefault("kind", "interval")
    body.setdefault("spec", "300")
    body.setdefault("prompt", "Poste um resumo do status no board.")
    return client.post(f"/api/agents/{slug}/schedules", json=body, headers=auth(token))


class TestScheduleCrud:
    def test_create_lists_and_arms(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        resp = _create(client, token, "backend-julio")
        assert resp.status_code == 201, resp.text
        sched = resp.json()
        assert sched["tools"] == "read" and sched["enabled"] is True
        assert sched["next_run_at"] is not None
        listed = client.get("/api/agents/backend-julio/schedules", headers=auth(token)).json()
        assert [s["id"] for s in listed] == [sched["id"]]

    def test_update_disable_then_run_now(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        sched = _create(client, token, "backend-julio").json()
        disabled = client.patch(
            f"/api/schedules/{sched['id']}", json={"enabled": False}, headers=auth(token)
        ).json()
        assert disabled["enabled"] is False and disabled["next_run_at"] is None
        ran = client.post(f"/api/schedules/{sched['id']}/run", headers=auth(token)).json()
        assert ran["enabled"] is True and ran["next_run_at"] is not None

    def test_delete(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        sched = _create(client, token, "backend-julio").json()
        assert (
            client.delete(f"/api/schedules/{sched['id']}", headers=auth(token)).status_code == 204
        )
        assert client.get(f"/api/schedules/{sched['id']}", headers=auth(token)).status_code == 404

    def test_bad_spec_is_422(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        # interval below the floor
        assert _create(client, token, "backend-julio", spec="5").status_code == 422
        # malformed cron
        assert _create(client, token, "backend-julio", kind="cron", spec="nope").status_code == 422


class TestOwnership:
    def test_cannot_schedule_another_users_agent(self, client):
        admin = do_setup(client)
        create_agent(client, admin, "backend-julio")  # admin's agent
        member = register_member(client, admin)
        # the member may not schedule the admin's agent
        assert _create(client, member, "backend-julio").status_code == 403

    def test_unknown_agent_is_404(self, client):
        token = do_setup(client)
        assert _create(client, token, "ghost").status_code == 404
