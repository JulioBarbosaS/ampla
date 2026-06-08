"""Hub app factory. Application state: engine, session_factory,
ConnectionManager and the auth rate limiter."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.errors import register_error_handlers
from app.api.routes import agents, auth, groups, invites, messages, users, ws
from app.core.config import Settings, get_settings
from app.core.db import build_engine, build_session_factory, create_tables
from app.core.ratelimit import SlidingWindowLimiter
from app.ws.connection_manager import ConnectionManager


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.validate_for_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = build_engine(settings.database_url)
        app.state.engine = engine
        app.state.session_factory = build_session_factory(engine)
        await create_tables(engine)
        yield
        await engine.dispose()

    app = FastAPI(title="Ampla Hub", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.manager = ConnectionManager()
    app.state.auth_limiter = SlidingWindowLimiter(
        max_events=settings.login_rate_per_minute, window_secs=60
    )
    app.state.broadcast_limiter = SlidingWindowLimiter(
        max_events=settings.broadcast_per_minute, window_secs=60
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    register_error_handlers(app)
    app.include_router(auth.router)
    app.include_router(invites.router)
    app.include_router(users.router)
    app.include_router(agents.router)
    app.include_router(groups.router)
    app.include_router(messages.router)
    app.include_router(ws.router)

    @app.get("/api/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok"}

    _mount_web_panel(app, settings)
    return app


def _mount_web_panel(app: FastAPI, settings: Settings) -> None:
    """Serve the built React panel (web/dist) at the same origin as the API —
    one URL, no CORS, GitLab-style. No-op when AMP_WEB_DIST is unset/absent
    (dev runs the panel via vite). Registered AFTER the API routers so /api
    and /ws win; everything else falls back to index.html for SPA routing."""
    if not settings.web_dist:
        return
    dist = Path(settings.web_dist)
    index = dist / "index.html"
    if not index.is_file():
        return
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api") or full_path == "ws":
            raise HTTPException(status_code=404)
        candidate = dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)  # favicon e afins
        return FileResponse(index)  # rota do React Router → SPA


app = create_app()
