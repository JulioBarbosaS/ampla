"""Hub app factory. Application state: engine, session_factory,
ConnectionManager and the auth rate limiter."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.deps import (
    build_approval_service,
    build_notification_service,
    build_preset_service,
)
from app.api.errors import register_error_handlers
from app.api.routes import (
    admin,
    agents,
    approvals,
    auth,
    groups,
    invites,
    messages,
    notifications,
    presets,
    users,
    ws,
)
from app.core.config import Settings, get_settings
from app.core.db import build_engine, build_session_factory, create_tables
from app.core.ratelimit import SlidingWindowLimiter
from app.repositories.hub_state_repo import HubStateRepository
from app.ws.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

# CSP for the bundled SPA: external JS/CSS from same origin, same-origin
# fetch + WebSocket (ws/wss), no framing, no plugins.
_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self' data:; connect-src 'self' ws: wss:; "
    "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.validate_for_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = build_engine(settings.database_url)
        app.state.engine = engine
        app.state.session_factory = build_session_factory(engine)
        await create_tables(engine)
        # Load the persisted global kill switch into app.state (seeding the row
        # on first boot) so the daemon hello_ack reflects it from the start.
        async with app.state.session_factory() as session:
            hub_state = await HubStateRepository(session).get()
            app.state.auto_responder_enabled = hub_state.auto_responder_enabled
            # Retention: prune old `done` notifications at startup (best-effort —
            # a failure here must never block boot). A live scheduler is future
            # work; for a local hub a startup sweep keeps the table bounded.
            try:
                pruned = await build_notification_service(session, settings).prune_done(
                    settings.notification_done_ttl_days
                )
                if pruned:
                    logger.info("retention: pruned %s done notifications", pruned)
            except Exception:
                logger.warning("notification retention prune failed", exc_info=True)
            # Auto-reject approvals left pending past the TTL (best-effort).
            try:
                expired = await build_approval_service(session, settings).expire_pending(
                    settings.approval_ttl_hours
                )
                if expired:
                    logger.info("expired %s stale pending approvals", expired)
            except Exception:
                logger.warning("approval expiry sweep failed", exc_info=True)
            # Seed the built-in guardrail presets (idempotent, best-effort).
            try:
                seeded = await build_preset_service(session).ensure_builtins()
                if seeded:
                    logger.info("seeded %s built-in guardrail presets", seeded)
            except Exception:
                logger.warning("guardrail preset seeding failed", exc_info=True)
        yield
        await engine.dispose()

    app = FastAPI(title="Ampla Hub", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.manager = ConnectionManager()
    # Safe default before the lifespan loads the persisted value from the DB,
    # so the WS route can always read state.auto_responder_enabled.
    app.state.auto_responder_enabled = True
    app.state.auth_limiter = SlidingWindowLimiter(
        max_events=settings.login_rate_per_minute, window_secs=60
    )
    app.state.broadcast_limiter = SlidingWindowLimiter(
        max_events=settings.broadcast_per_minute, window_secs=60
    )
    # Per-user limit for panel sends over REST (the WS path has its own bucket).
    app.state.message_limiter = SlidingWindowLimiter(
        max_events=settings.ws_messages_per_minute, window_secs=60
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
        response.headers["Content-Security-Policy"] = _CSP
        # Ignored by browsers over plain HTTP; takes effect behind a TLS proxy.
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    register_error_handlers(app)
    app.include_router(auth.router)
    app.include_router(invites.router)
    app.include_router(users.router)
    app.include_router(agents.router)
    app.include_router(groups.router)
    app.include_router(messages.router)
    app.include_router(admin.router)
    app.include_router(notifications.router)
    app.include_router(approvals.router)
    app.include_router(presets.router)
    app.include_router(ws.router)

    @app.get("/api/health", tags=["health"])
    async def health() -> dict:
        """Liveness: the process is up and answering."""
        return {"status": "ok"}

    @app.get("/api/health/ready", tags=["health"])
    async def readiness() -> dict:
        """Readiness: the database is reachable (used by the container
        HEALTHCHECK and orchestrators). Returns 503 if a query can't run."""
        try:
            async with app.state.session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Banco de dados indisponível."
            ) from exc
        return {"status": "ready"}

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
