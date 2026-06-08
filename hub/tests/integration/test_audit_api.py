"""Audit trail is admin-only and actually reviewable (events are recorded
across the services; GET /api/users/audit is the way to see them)."""

from tests.helpers import auth, do_setup, register_member


def test_admin_sees_audit_member_forbidden(client):
    admin = do_setup(client)
    member = register_member(client, admin)

    response = client.get("/api/users/audit", headers=auth(admin))
    assert response.status_code == 200
    events = {e["event"] for e in response.json()}
    assert "setup" in events  # the admin bootstrap was recorded

    assert client.get("/api/users/audit", headers=auth(member)).status_code == 403
