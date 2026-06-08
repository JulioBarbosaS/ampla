"""Liveness answers always; readiness reflects the database."""


def test_liveness_is_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_ok_when_db_reachable(client):
    response = client.get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_503_when_db_unreachable(client):
    def boom():
        raise RuntimeError("database gone")

    client.app.state.session_factory = boom  # next readiness probe fails to query
    response = client.get("/api/health/ready")
    assert response.status_code == 503
