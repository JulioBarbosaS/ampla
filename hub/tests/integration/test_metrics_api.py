"""Instance observability (GET /api/admin/metrics): admin-only, and the windowed
roll-up over autorespond_runs + messages + audit_log."""

import pytest

from tests.helpers import (
    auth,
    connect_agent_ws,
    create_agent,
    create_key,
    do_setup,
    recv_until,
    register_member,
)

RECORD = {
    "trigger_message_id": 7,
    "from_sender": "mobile-eduardo",
    "result": "blocked",
    "reason": "secret in output",
    "reply_preview": "",
    "tools_allowed": "Read,Grep,Glob",
    "tools_disallowed": "Bash,Write",
    "guardrails": {"allow_write": False, "sandbox": "docker"},
    "duration_ms": 1234,
    "timed_out": True,
    "input_tokens": 100,
    "output_tokens": 10,
    "cost_usd": 0.02,
}


class TestMetrics:
    def test_requires_admin(self, client):
        admin = do_setup(client)
        member = register_member(client, admin)
        assert client.get("/api/admin/metrics", headers=auth(member)).status_code == 403
        client.cookies.clear()
        assert client.get("/api/admin/metrics").status_code == 401

    def test_empty_instance_is_all_zeros(self, client):
        token = do_setup(client)
        body = client.get("/api/admin/metrics?days=7", headers=auth(token)).json()
        assert body["window_days"] == 7
        assert body["messages_total"] == 0
        assert body["autorespond"]["total_runs"] == 0
        assert body["autorespond"]["by_result"] == {}
        assert body["autorespond_daily"] == []
        assert "generated_at" in body
        # setup itself is audited → at least one event family is present
        assert any(e["count"] >= 1 for e in body["audit_events"])

    def test_clamps_the_window(self, client):
        token = do_setup(client)
        assert client.get("/api/admin/metrics?days=0", headers=auth(token)).status_code == 422
        assert client.get("/api/admin/metrics?days=91", headers=auth(token)).status_code == 422

    def test_aggregates_runs_messages_and_events(self, client):
        admin = do_setup(client)
        create_agent(client, admin, "backend-julio")
        create_agent(client, admin, "mobile-eduardo")
        key = create_key(client, admin, "backend-julio")
        with connect_agent_ws(client, "backend-julio", key) as ws:
            recv_until(ws, "hello_ack")
            ws.send_json({"type": "message", "to": "mobile-eduardo", "body": "oi"})
            ws.send_json({"type": "autorespond_report", "record": RECORD})
            ws.send_json({"type": "message"})  # invalid → flushes the prior commits
            assert recv_until(ws, "error")["code"] == "bad_frame"

        body = client.get("/api/admin/metrics", headers=auth(admin)).json()
        assert body["messages_total"] >= 1
        ar = body["autorespond"]
        assert ar["total_runs"] == 1
        assert ar["by_result"] == {"blocked": 1}
        assert ar["timed_out"] == 1
        assert ar["total_output_tokens"] == 10
        assert ar["total_input_tokens"] == 100
        assert ar["total_cost_usd"] == pytest.approx(0.02)
        assert len(body["autorespond_daily"]) == 1
        assert body["autorespond_daily"][0]["runs"] == 1
        # event families recorded while seeding (setup/agent/key creation)
        assert "agent_created" in {e["event"] for e in body["audit_events"]}
