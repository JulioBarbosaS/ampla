"""Setup do admin, registro por convite, login com lockout incremental."""

from datetime import timedelta

from app.core import security
from app.core.config import Settings
from app.models.user import Invite, User, utcnow
from app.repositories.audit_repo import AuditRepository
from app.repositories.invite_repo import InviteRepository
from app.repositories.user_repo import UserRepository
from app.services.errors import (
    AccountLockedError,
    AuthError,
    ConflictError,
    PermissionDeniedError,
)

GENERIC_LOGIN_ERROR = "Email ou senha incorretos."
MAX_LOCKOUT_SECS = 3600


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        invites: InviteRepository,
        audit: AuditRepository,
        settings: Settings,
    ) -> None:
        self._users = users
        self._invites = invites
        self._audit = audit
        self._settings = settings

    # ---- setup (primeiro usuário = admin) ----

    async def needs_setup(self) -> bool:
        return await self._users.count() == 0

    async def setup_admin(self, email: str, name: str, password: str) -> tuple[User, str]:
        if not await self.needs_setup():
            raise ConflictError("Setup já realizado.")
        user = await self._users.add(
            User(
                email=email.lower(),
                name=name,
                password_hash=security.hash_password(password),
                role="admin",
            )
        )
        await self._audit.record("setup", actor=user.email)
        return user, self._issue_token(user)

    # ---- registro por convite ----

    async def register(
        self, invite_code: str, email: str, name: str, password: str
    ) -> tuple[User, str]:
        invite = await self._invites.get_by_code(invite_code.strip().upper())
        if invite is None or invite.used_at is not None or invite.expires_at < utcnow():
            await self._audit.record(
                "register_fail", actor=email.lower(), detail={"reason": "invite"}
            )
            raise PermissionDeniedError("Convite inválido, expirado ou já utilizado.")
        if await self._users.get_by_email(email.lower()) is not None:
            raise ConflictError("Já existe uma conta com este email.")
        user = await self._users.add(
            User(
                email=email.lower(),
                name=name,
                password_hash=security.hash_password(password),
                role="member",
            )
        )
        invite.used_by = user.id
        invite.used_at = utcnow()
        await self._invites.save(invite)
        await self._audit.record("register", actor=user.email, detail={"invite": invite.code})
        return user, self._issue_token(user)

    # ---- convites ----

    async def create_invite(self, actor: User) -> Invite:
        if actor.role != "admin":
            raise PermissionDeniedError("Apenas administradores geram convites.")
        invite = await self._invites.add(
            Invite(
                code=security.generate_invite_code(),
                created_by=actor.id,
                expires_at=utcnow() + timedelta(hours=self._settings.invite_expires_hours),
            )
        )
        await self._audit.record("invite_created", actor=actor.email, detail={"code": invite.code})
        return invite

    async def list_invites(self, actor: User) -> list[Invite]:
        if actor.role != "admin":
            raise PermissionDeniedError("Apenas administradores listam convites.")
        return await self._invites.list_all()

    # ---- login com lockout incremental (Ameaça 2) ----

    async def login(self, email: str, password: str) -> tuple[User, str]:
        user = await self._users.get_by_email(email.lower())
        if user is None:
            # bcrypt dummy para igualar o tempo de resposta (anti user-enumeration)
            security.verify_password(password, security.hash_password("timing-equalizer"))
            await self._audit.record("login_fail", actor=email.lower())
            raise AuthError(GENERIC_LOGIN_ERROR)

        if user.locked_until is not None and user.locked_until > utcnow():
            await self._audit.record("login_locked", actor=user.email)
            raise AccountLockedError("Conta temporariamente bloqueada. Tente novamente mais tarde.")

        if not security.verify_password(password, user.password_hash):
            user.failed_logins += 1
            overflow = user.failed_logins - self._settings.login_max_attempts
            if overflow >= 0:
                lock_secs = min(
                    self._settings.login_lockout_base_secs * (2**overflow), MAX_LOCKOUT_SECS
                )
                user.locked_until = utcnow() + timedelta(seconds=lock_secs)
            await self._users.save(user)
            await self._audit.record("login_fail", actor=user.email)
            raise AuthError(GENERIC_LOGIN_ERROR)

        user.failed_logins = 0
        user.locked_until = None
        await self._users.save(user)
        await self._audit.record("login_ok", actor=user.email)
        return user, self._issue_token(user)

    # ---- resolução de token (usada pelo middleware/deps) ----

    async def get_user_by_token(self, token: str) -> User | None:
        user_id = security.decode_jwt(token, self._settings.jwt_secret)
        if user_id is None:
            return None
        return await self._users.get_by_id(user_id)

    def _issue_token(self, user: User) -> str:
        return security.create_jwt(
            user.id, self._settings.jwt_secret, self._settings.jwt_expires_days
        )
