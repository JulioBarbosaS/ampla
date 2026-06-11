"""Dependency injection: session → repositories → services.

Routes only know services (docs/ARCHITECTURE.md · layer rules).
"""

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.cookies import SESSION_COOKIE
from app.models.user import User
from app.repositories.agent_repo import AgentRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.group_repo import GroupRepository
from app.repositories.hub_state_repo import HubStateRepository
from app.repositories.invite_repo import InviteRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.user_repo import UserRepository
from app.services.admin_service import AdminService
from app.services.agent_service import AgentService
from app.services.auth_service import AuthService
from app.services.group_service import GroupService
from app.services.message_service import MessageService

_bearer = HTTPBearer(auto_error=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


# ---- pure factories (the only place that wires service+repositories) ----
# Used by the REST dependencies below AND by the WS route (one session per operation).


def build_auth_service(session: AsyncSession, settings) -> AuthService:
    return AuthService(
        users=UserRepository(session),
        invites=InviteRepository(session),
        audit=AuditRepository(session),
        settings=settings,
    )


def build_agent_service(session: AsyncSession) -> AgentService:
    return AgentService(
        agents=AgentRepository(session),
        audit=AuditRepository(session),
        groups=GroupRepository(session),
    )


def build_group_service(session: AsyncSession) -> GroupService:
    return GroupService(
        groups=GroupRepository(session),
        agents=AgentRepository(session),
        audit=AuditRepository(session),
    )


def build_message_service(session: AsyncSession, settings) -> MessageService:
    return MessageService(
        messages=MessageRepository(session),
        agents=AgentRepository(session),
        audit=AuditRepository(session),
        settings=settings,
    )


def build_admin_service(session: AsyncSession) -> AdminService:
    return AdminService(state=HubStateRepository(session), audit=AuditRepository(session))


def get_app_settings(request: Request) -> Settings:
    """The Settings the app was built with (tests inject their own — never the
    module-level get_settings cache)."""
    return request.app.state.settings


def get_auth_service(request: Request, session: AsyncSession = Depends(get_session)) -> AuthService:
    return build_auth_service(session, request.app.state.settings)


def get_agent_service(session: AsyncSession = Depends(get_session)) -> AgentService:
    return build_agent_service(session)


def get_group_service(session: AsyncSession = Depends(get_session)) -> GroupService:
    return build_group_service(session)


def get_message_service(
    request: Request, session: AsyncSession = Depends(get_session)
) -> MessageService:
    return build_message_service(session, request.app.state.settings)


def get_admin_service(session: AsyncSession = Depends(get_session)) -> AdminService:
    return build_admin_service(session)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    auth: AuthService = Depends(get_auth_service),
) -> User:
    # Header first (deliberate, used by the CLI/tests), cookie as fallback (the
    # web panel, which keeps the JWT out of JavaScript reach). An explicit
    # Authorization header always wins over an ambient cookie.
    token = (credentials.credentials if credentials else None) or request.cookies.get(
        SESSION_COOKIE
    )
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Não autenticado.")
    user = await auth.get_user_by_token(token)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão inválida ou expirada.")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Gate for instance-wide admin routes (kill switch). 403 for non-admins."""
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas administradores.")
    return user


def auth_rate_limit(request: Request) -> None:
    """Per-IP rate limit on the authentication routes (Threat 2)."""
    client_ip = request.client.host if request.client else "unknown"
    if not request.app.state.auth_limiter.allow(client_ip):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Muitas tentativas. Aguarde um minuto."
        )
