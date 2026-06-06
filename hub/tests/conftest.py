import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def make_settings(**overrides) -> Settings:
    defaults = dict(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret="test-secret-com-32-bytes-no-minimo!",
        cors_origins=["http://testserver"],
    )
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
