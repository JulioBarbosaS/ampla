"""Auto-respond transcript (Epic 03 · 3.1): the daemon reports a run over the WS,
the hub persists it under the AUTHENTICATED agent, and owner/admin read it."""

from tests.helpers import (
    auth,
    connect_agent_ws,
    create_agent,
    create_key,
    do_setup,
    recv_until,
    register_member,
)

SAMPLE_RECORD = {
    "trigger_message_id": 42,
    "from_sender": "mobile-eduardo",
    "result": "replied",
    "reason": None,
    "reply_preview": "Sim: POST /api/v1/auth/password-reset",
    "tools_allowed": "Read,Grep,Glob",
    "tools_disallowed": "Bash,NotebookEdit,WebFetch,WebSearch,Edit,Write",
    "guardrails": {"allow_write": False, "trusted_sender": False, "sandbox": "host"},
    "duration_ms": 1234,
    "timed_out": False,
    "input_tokens": None,
    "output_tokens": None,
    "cost_usd": None,
}


def _report(client, slug: str, key: str, record: dict) -> None:
    """Sends a report on the daemon WS, then flushes: the receive loop is
    sequential, so a deliberately invalid frame's `bad_frame` error coming back
    proves the prior report was already committed — no broadcast/heartbeat
    dependence."""
    with connect_agent_ws(client, slug, key) as ws:
        recv_until(ws, "hello_ack")
        ws.send_json({"type": "autorespond_report", "record": record})
        ws.send_json({"type": "message"})  # missing to/body → bad_frame
        assert recv_until(ws, "error")["code"] == "bad_frame"


class TestTranscript:
    def test_report_persists_and_owner_reads_it(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        key = create_key(client, token, "backend-julio")
        _report(client, "backend-julio", key, SAMPLE_RECORD)

        runs = client.get("/api/agents/backend-julio/autorespond-runs", headers=auth(token)).json()
        assert len(runs) == 1
        row = runs[0]
        assert row["agent_slug"] == "backend-julio"  # attributed to the socket
        assert row["trigger_message_id"] == 42
        assert row["result"] == "replied"
        assert row["reply_preview"].endswith("password-reset")
        assert row["guardrails"]["sandbox"] == "host"
        assert row["input_tokens"] is None

    def test_record_carries_no_agent_id_so_it_cannot_be_spoofed(self, client):
        """The frame has no agent_id; the run is always stored under the
        authenticated socket — a daemon cannot attribute a run to another agent."""
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        key = create_key(client, token, "backend-julio")
        # Even a record naming another agent is ignored: extra keys aren't fields.
        _report(client, "backend-julio", key, {**SAMPLE_RECORD, "agent_id": "mobile-eduardo"})

        mine = client.get("/api/agents/backend-julio/autorespond-runs", headers=auth(token)).json()
        other = client.get(
            "/api/agents/mobile-eduardo/autorespond-runs", headers=auth(token)
        ).json()
        assert len(mine) == 1
        assert other == []

    def test_non_owner_member_forbidden(self, client):
        admin = do_setup(client)
        member = register_member(client, admin)
        create_agent(client, admin, "backend-julio")
        resp = client.get("/api/agents/backend-julio/autorespond-runs", headers=auth(member))
        assert resp.status_code == 403

    def test_admin_wide_listing(self, client):
        admin = do_setup(client)
        member = register_member(client, admin)
        create_agent(client, admin, "backend-julio")
        key = create_key(client, admin, "backend-julio")
        _report(client, "backend-julio", key, SAMPLE_RECORD)

        all_runs = client.get("/api/admin/autorespond-runs", headers=auth(admin)).json()
        assert len(all_runs) == 1
        # a member cannot see the instance-wide transcript
        assert client.get("/api/admin/autorespond-runs", headers=auth(member)).status_code == 403


class TestEscalation:
    """A non-answer routes the trigger to the owner's Inbox (Epic 04 · 4.3) —
    exercises the full WS → record_run → notification path (deps wiring)."""

    def test_failed_run_escalates_to_the_owner_inbox(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")  # escalate_on defaults to failed+blocked
        key = create_key(client, token, "backend-julio")
        _report(
            client,
            "backend-julio",
            key,
            {**SAMPLE_RECORD, "result": "failed", "reason": "timeout", "reply_preview": ""},
        )

        notes = client.get("/api/notifications", headers=auth(token)).json()
        escalations = [n for n in notes if n["reason"] == "escalation"]
        assert len(escalations) == 1
        assert escalations[0]["agent_slug"] == "backend-julio"

    def test_replied_run_does_not_escalate(self, client):
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        key = create_key(client, token, "backend-julio")
        _report(client, "backend-julio", key, SAMPLE_RECORD)  # result=replied

        notes = client.get("/api/notifications", headers=auth(token)).json()
        assert [n for n in notes if n["reason"] == "escalation"] == []
