"""Injeção de dependências: sessão → repositories → services.

Rotas só conhecem services (docs/ARCHITECTURE.md · Regras de camadas).
"""

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.agent_repo import AgentRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.invite_repo import InviteRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.user_repo import UserRepository
from app.services.agent_service import AgentService
from app.services.auth_service import AuthService
from app.services.message_service import MessageService

_bearer = HTTPBearer(auto_error=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_auth_service(request: Request, session: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService(
        users=UserRepository(session),
        invites=InviteRepository(session),
        audit=AuditRepository(session),
        settings=request.app.state.settings,
    )


def get_agent_service(session: AsyncSession = Depends(get_session)) -> AgentService:
    return AgentService(agents=AgentRepository(session), audit=AuditRepository(session))


def get_message_service(
    request: Request, session: AsyncSession = Depends(get_session)
) -> MessageService:
    return MessageService(
        messages=MessageRepository(session),
        agents=AgentRepository(session),
        audit=AuditRepository(session),
        settings=request.app.state.settings,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    auth: AuthService = Depends(get_auth_service),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Não autenticado.")
    user = await auth.get_user_by_token(credentials.credentials)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão inválida ou expirada.")
    return user


def auth_rate_limit(request: Request) -> None:
    """Rate limit por IP nas rotas de autenticação (Ameaça 2)."""
    client_ip = request.client.host if request.client else "unknown"
    if not request.app.state.auth_limiter.allow(client_ip):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Muitas tentativas. Aguarde um minuto."
        )
