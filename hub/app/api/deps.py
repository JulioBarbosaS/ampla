"""Dependency injection: session → repositories → services.

Routes only know services (docs/ARCHITECTURE.md · layer rules).
"""

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.cookies import SESSION_COOKIE
from app.models.message import Message
from app.models.user import User
from app.repositories.agent_repo import AgentRepository
from app.repositories.approval_repo import ApprovalRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.autorespond_repo import AutorespondRunRepository
from app.repositories.delegation_repo import DelegationRepository
from app.repositories.group_repo import GroupRepository
from app.repositories.guardrail_preset_repo import GuardrailPresetRepository
from app.repositories.hub_state_repo import HubStateRepository
from app.repositories.invite_repo import InviteRepository
from app.repositories.kanban_repo import KanbanRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.notification_repo import NotificationRepository
from app.repositories.user_repo import UserRepository
from app.schemas.message import MessageOut
from app.services.admin_service import AdminService
from app.services.agent_service import AgentService
from app.services.approval_service import ApprovalService
from app.services.auth_service import AuthService
from app.services.autorespond_service import AutorespondService
from app.services.delegation_service import DelegationService
from app.services.group_service import GroupService
from app.services.kanban_service import KanbanService
from app.services.message_service import MessageService
from app.services.notification_service import NotificationService
from app.services.preset_service import PresetService

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


def _notification_publisher(manager):
    """Adapts the connection manager into the abstract publisher the service
    awaits — keeps NotificationService free of any transport import."""

    async def publish(user_id: int, payload: dict) -> None:
        await manager.notify_user(user_id, payload)

    return publish


def build_notification_service(
    session: AsyncSession, settings, manager=None
) -> NotificationService:
    return NotificationService(
        notifications=NotificationRepository(session),
        users=UserRepository(session),
        publisher=_notification_publisher(manager) if manager is not None else None,
        max_new_per_hour=settings.notification_max_new_per_hour,
    )


def build_message_service(session: AsyncSession, settings, manager=None) -> MessageService:
    return MessageService(
        messages=MessageRepository(session),
        agents=AgentRepository(session),
        audit=AuditRepository(session),
        settings=settings,
        notifications=build_notification_service(session, settings, manager),
        # delegations lets a reply close a delegated task (Epic 04 · 4.4).
        delegations=DelegationRepository(session),
    )


def build_preset_service(session: AsyncSession) -> PresetService:
    return PresetService(
        presets=GuardrailPresetRepository(session),
        agents=AgentRepository(session),
        audit=AuditRepository(session),
    )


def build_admin_service(session: AsyncSession) -> AdminService:
    return AdminService(state=HubStateRepository(session), audit=AuditRepository(session))


def build_kanban_service(session: AsyncSession) -> KanbanService:
    return KanbanService(
        boards=KanbanRepository(session),
        audit=AuditRepository(session),
        agents=AgentRepository(session),
    )


def build_autorespond_service(
    session: AsyncSession, settings=None, manager=None
) -> AutorespondService:
    # agents + notifications power escalation (Epic 04 · 4.3). The read routes
    # build it without settings/manager (no escalation needed there); the WS
    # record_run path passes both so escalations push to the owner in real time.
    notifications = (
        build_notification_service(session, settings, manager) if settings is not None else None
    )
    return AutorespondService(
        runs=AutorespondRunRepository(session),
        agents=AgentRepository(session),
        notifications=notifications,
    )


def _approval_sender(session: AsyncSession, settings, manager):
    """Sends the approved reply AS the agent and delivers it — the same
    persist + real-time push the REST /api/messages path uses. Keeps
    ApprovalService free of any transport import."""
    messages = build_message_service(session, settings, manager)

    async def send_and_deliver(
        from_slug: str, to_slug: str, body: str, in_reply_to: int | None
    ) -> Message:
        msg = await messages.send(
            from_slug, to_slug, body, type="response", in_reply_to=in_reply_to
        )
        if manager is not None:
            out = MessageOut.model_validate(msg)
            frame = {"type": "message", "message": out.model_dump(mode="json", by_alias=True)}
            if await manager.send_to_agent(to_slug, frame):
                await messages.mark_delivered([msg.id])
            await manager.notify_message(frame, from_slug, to_slug)
        return msg

    return send_and_deliver


def build_approval_service(session: AsyncSession, settings, manager=None) -> ApprovalService:
    return ApprovalService(
        approvals=ApprovalRepository(session),
        agents=AgentRepository(session),
        audit=AuditRepository(session),
        notifications=build_notification_service(session, settings, manager),
        sender=_approval_sender(session, settings, manager),
    )


def _delegation_sender(session: AsyncSession, settings, manager):
    """Sends the delegated task AS the delegator (type=task) and dispatches it —
    the same persist + real-time push the message path uses — so it reaches the
    delegate's daemon and triggers its auto-respond. Keeps DelegationService free
    of any transport import. Raises PermissionDeniedError on the delegate's
    allowlist block, which the service turns into a `declined` delegation."""
    messages = build_message_service(session, settings, manager)

    async def send_task(from_slug: str, to_slug: str, body: str) -> Message:
        msg = await messages.send(from_slug, to_slug, body, type="task")
        if manager is not None:
            out = MessageOut.model_validate(msg)
            frame = {"type": "message", "message": out.model_dump(mode="json", by_alias=True)}
            if await manager.send_to_agent(to_slug, frame):
                await messages.mark_delivered([msg.id])
            await manager.notify_message(frame, from_slug, to_slug)
        return msg

    return send_task


def build_delegation_service(session: AsyncSession, settings, manager=None) -> DelegationService:
    return DelegationService(
        delegations=DelegationRepository(session),
        agents=AgentRepository(session),
        audit=AuditRepository(session),
        sender=_delegation_sender(session, settings, manager),
    )


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
    return build_message_service(session, request.app.state.settings, request.app.state.manager)


def get_admin_service(session: AsyncSession = Depends(get_session)) -> AdminService:
    return build_admin_service(session)


def get_kanban_service(session: AsyncSession = Depends(get_session)) -> KanbanService:
    return build_kanban_service(session)


def get_preset_service(session: AsyncSession = Depends(get_session)) -> PresetService:
    return build_preset_service(session)


def get_autorespond_service(session: AsyncSession = Depends(get_session)) -> AutorespondService:
    return build_autorespond_service(session)


def get_approval_service(
    request: Request, session: AsyncSession = Depends(get_session)
) -> ApprovalService:
    return build_approval_service(session, request.app.state.settings, request.app.state.manager)


def get_notification_service(
    request: Request, session: AsyncSession = Depends(get_session)
) -> NotificationService:
    return build_notification_service(
        session, request.app.state.settings, request.app.state.manager
    )


def get_delegation_service(
    request: Request, session: AsyncSession = Depends(get_session)
) -> DelegationService:
    return build_delegation_service(session, request.app.state.settings, request.app.state.manager)


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
