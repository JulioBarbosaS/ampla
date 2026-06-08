"""Panel sends over REST get their own per-user rate limit (the WS path has
a token bucket; without this a logged-in user could flood via REST)."""

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings
from tests.helpers import auth, create_agent, do_setup


def test_rest_send_is_rate_limited():
    app = create_app(make_settings(ws_messages_per_minute=3))
    with TestClient(app) as client:
        token = do_setup(client)
        create_agent(client, token, "backend-julio")
        create_agent(client, token, "mobile-eduardo")
        codes = [
            client.post(
                "/api/messages",
                json={"from": "backend-julio", "to": "mobile-eduardo", "body": f"m{i}"},
                headers=auth(token),
            ).status_code
            for i in range(6)
        ]
        assert codes[0] == 201
        assert 429 in codes  # flood is cut off within the window
