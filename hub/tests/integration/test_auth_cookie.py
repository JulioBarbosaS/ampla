"""The web panel authenticates with an HttpOnly session cookie (the JWT never
reaches JavaScript). The Bearer header keeps working for the CLI/tests, and
takes precedence over an ambient cookie."""

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings
from tests.helpers import ADMIN, auth, do_setup, recv_until


def test_login_sets_httponly_samesite_cookie(client):
    response = client.post("/api/auth/setup", json=ADMIN)
    assert response.status_code == 200

    cookie = response.headers["set-cookie"].lower()
    assert "amp_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/" in cookie
    assert "secure" not in cookie  # dev: plain HTTP, no Secure flag


def test_cookie_authenticates_without_bearer(client):
    do_setup(client)  # the TestClient jar now holds amp_session

    # no Authorization header — only the cookie carries the session
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == ADMIN["email"]


def test_logout_clears_the_session(client):
    do_setup(client)
    assert client.get("/api/auth/me").status_code == 200

    assert client.post("/api/auth/logout").status_code == 204
    # cookie expired and dropped → no credential left
    assert client.get("/api/auth/me").status_code == 401


def test_bearer_still_authenticates_without_a_cookie(client):
    """The CLI path: a Bearer header authenticates with no cookie in play."""
    token = do_setup(client)
    client.cookies.clear()  # drop the session cookie; rely purely on the header

    response = client.get("/api/auth/me", headers=auth(token))
    assert response.status_code == 200
    assert response.json()["email"] == ADMIN["email"]

    # with neither header nor cookie there is no credential at all
    assert client.get("/api/auth/me").status_code == 401


def test_session_cookie_secure_follows_the_request_scheme():
    # Secure tracks the CONNECTION, not the env: it is dropped over plain
    # http://localhost (the URL the quickstart opens) and set over HTTPS — so a
    # production image still lets you log in on localhost while real TLS gets it.
    settings = make_settings(
        environment="production",
        jwt_secret="prod-secret-com-32-bytes-no-minimo!",
    )
    with TestClient(create_app(settings), base_url="http://testserver") as http_client:
        r = http_client.post("/api/auth/setup", json=ADMIN)
        assert r.status_code == 200
        assert "secure" not in r.headers["set-cookie"].lower()  # http → not Secure
    with TestClient(create_app(settings), base_url="https://testserver") as https_client:
        r = https_client.post("/api/auth/setup", json=ADMIN)
        assert r.status_code == 200
        assert "secure" in r.headers["set-cookie"].lower()  # https → Secure


def test_observer_connects_via_session_cookie(client):
    """The browser carries the cookie on the WS upgrade; the observer hello no
    longer needs to ship the JWT in the frame."""
    do_setup(client)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "hello"})  # no jwt — the cookie authenticates
        assert recv_until(ws, "hello_ack")["type"] == "hello_ack"
