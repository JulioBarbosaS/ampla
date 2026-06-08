"""Admin setup, invite-based registration, login with incremental lockout."""

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
    NotFoundError,
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

    # ---- setup (first user = admin) ----

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

    # ---- invite-based registration ----

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

    # ---- invites ----

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

    # ---- user management (admin) ----

    async def list_users(self, actor: User) -> list[User]:
        if actor.role != "admin":
            raise PermissionDeniedError("Apenas administradores listam usuários.")
        return await self._users.list_all()

    async def set_role(self, actor: User, target_id: int, role: str) -> User:
        """Promotes/demotes a user. Admin-only. Guardrail: never demote the
        last admin (otherwise the instance is orphaned, with no one to administer it)."""
        if actor.role != "admin":
            raise PermissionDeniedError("Apenas administradores alteram papéis.")
        target = await self._users.get_by_id(target_id)
        if target is None:
            raise NotFoundError("Usuário não encontrado.")
        if target.role == role:
            return target  # idempotent
        if role == "member" and target.role == "admin" and await self._users.count_admins() <= 1:
            raise ConflictError("Não é possível rebaixar o último administrador.")
        target.role = role
        await self._users.save(target)
        await self._audit.record(
            "role_changed", actor=actor.email, detail={"target": target.email, "role": role}
        )
        return target

    # ---- login with incremental lockout (Threat 2) ----

    async def login(self, email: str, password: str) -> tuple[User, str]:
        user = await self._users.get_by_email(email.lower())
        if user is None:
            # Compares against a precomputed CONSTANT bcrypt hash: a single
            # verification, matching the timing of the real path (which also does
            # one verification). Generating a fresh hash here cost ~2x and created
            # an inverted enumeration oracle (Threat 2).
            security.verify_password(password, security.DUMMY_PASSWORD_HASH)
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

    # ---- token resolution (used by the middleware/deps) ----

    async def get_user_by_token(self, token: str) -> User | None:
        user_id = security.decode_jwt(token, self._settings.jwt_secret)
        if user_id is None:
            return None
        return await self._users.get_by_id(user_id)

    def _issue_token(self, user: User) -> str:
        return security.create_jwt(
            user.id, self._settings.jwt_secret, self._settings.jwt_expires_days
        )
