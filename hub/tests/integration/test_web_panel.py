"""When AMP_WEB_DIST points to a built panel, the hub serves the UI at the
same origin as the API (one URL, no CORS) with SPA fallback — while /api
and /ws keep working."""

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings


def _build_dist(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Ampla</title>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('amp')")
    return tmp_path


def test_serves_panel_and_keeps_api(tmp_path):
    app = create_app(make_settings(web_dist=str(_build_dist(tmp_path))))
    with TestClient(app) as client:
        # raiz e rota do React Router caem no index.html (SPA)
        assert "Ampla" in client.get("/").text
        assert "Ampla" in client.get("/groups").text
        # asset real é servido
        assert client.get("/assets/app.js").text == "console.log('amp')"
        # a API continua funcionando e não é engolida pelo catch-all
        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.get("/api/inexistente").status_code != 200


def test_no_panel_when_web_dist_unset(tmp_path):
    app = create_app(make_settings())  # web_dist None → não monta
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        # sem painel montado, a raiz não vira index.html
        assert client.get("/").status_code == 404


def test_security_headers_present():
    app = create_app(make_settings())
    with TestClient(app) as client:
        h = client.get("/api/health").headers
        assert "default-src 'self'" in h["content-security-policy"]
        assert "frame-ancestors 'none'" in h["content-security-policy"]
        assert h["strict-transport-security"].startswith("max-age=")
        assert h["x-content-type-options"] == "nosniff"
