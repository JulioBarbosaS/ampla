"""App factory do hub. Estado da aplicação: engine, session_factory,
ConnectionManager e rate limiter de auth."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_error_handlers
from app.api.routes import agents, auth, invites, messages, ws
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

    app = FastAPI(title="AMP Hub", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.manager = ConnectionManager()
    app.state.auth_limiter = SlidingWindowLimiter(
        max_events=settings.login_rate_per_minute, window_secs=60
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
    app.include_router(agents.router)
    app.include_router(messages.router)
    app.include_router(ws.router)

    @app.get("/api/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
