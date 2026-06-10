from datetime import timedelta

import pytest

from app.models.user import utcnow
from app.services.auth_service import GENERIC_LOGIN_ERROR, AuthService
from app.services.errors import (
    AccountLockedError,
    AuthError,
    ConflictError,
    PermissionDeniedError,
)
from tests.conftest import make_settings
from tests.unit.fakes import FakeAuditRepository, FakeInviteRepository, FakeUserRepository

EMAIL = "julio@amp.local"
PASSWORD = "senha-muito-segura-1"


@pytest.fixture
def audit() -> FakeAuditRepository:
    return FakeAuditRepository()


@pytest.fixture
def service(audit) -> AuthService:
    return AuthService(
        users=FakeUserRepository(),
        invites=FakeInviteRepository(),
        audit=audit,
        settings=make_settings(login_max_attempts=3, login_lockout_base_secs=30),
    )


async def make_admin(service: AuthService):
    user, token = await service.setup_admin(EMAIL, "Julio", PASSWORD)
    return user, token


class TestSetup:
    async def test_needs_setup_only_without_users(self, service):
        assert await service.needs_setup() is True
        await make_admin(service)
        assert await service.needs_setup() is False

    async def test_first_user_becomes_admin(self, service):
        user, token = await make_admin(service)
        assert user.role == "admin"
        assert token
        assert (await service.get_user_by_token(token)).id == user.id

    async def test_setup_second_time_fails(self, service):
        await make_admin(service)
        with pytest.raises(ConflictError):
            await service.setup_admin("outro@amp.local", "Outro", PASSWORD)


class TestRegister:
    async def test_registration_with_valid_invite(self, service):
        admin, _ = await make_admin(service)
        invite = await service.create_invite(admin)
        user, token = await service.register(
            invite.code, "dev@amp.local", "Dev", "senha-do-dev-123"
        )
        assert user.role == "member"
        assert invite.used_by == user.id
        assert token

    async def test_nonexistent_invite(self, service):
        with pytest.raises(PermissionDeniedError):
            await service.register("AMP-XXXX-XXXX-XXXX-XXXX", "a@b.c", "A", PASSWORD)

    async def test_expired_invite(self, service):
        admin, _ = await make_admin(service)
        invite = await service.create_invite(admin)
        invite.expires_at = utcnow() - timedelta(hours=1)
        with pytest.raises(PermissionDeniedError):
            await service.register(invite.code, "a@b.c", "A", PASSWORD)

    async def test_single_use_invite(self, service):
        admin, _ = await make_admin(service)
        invite = await service.create_invite(admin)
        await service.register(invite.code, "dev@amp.local", "Dev", PASSWORD)
        with pytest.raises(PermissionDeniedError):
            await service.register(invite.code, "dev2@amp.local", "Dev2", PASSWORD)

    async def test_duplicate_email(self, service):
        admin, _ = await make_admin(service)
        invite = await service.create_invite(admin)
        with pytest.raises(ConflictError):
            await service.register(invite.code, EMAIL, "Clone", PASSWORD)

    async def test_member_does_not_generate_invite(self, service):
        admin, _ = await make_admin(service)
        invite = await service.create_invite(admin)
        member, _ = await service.register(invite.code, "dev@amp.local", "Dev", PASSWORD)
        with pytest.raises(PermissionDeniedError):
            await service.create_invite(member)


class TestLogin:
    async def test_login_ok(self, service, audit):
        await make_admin(service)
        user, token = await service.login(EMAIL, PASSWORD)
        assert user.email == EMAIL
        assert token
        assert audit.has("login_ok")

    async def test_wrong_password_generic_message(self, service):
        await make_admin(service)
        with pytest.raises(AuthError, match=GENERIC_LOGIN_ERROR):
            await service.login(EMAIL, "senha-errada-123")

    async def test_nonexistent_email_same_generic_message(self, service):
        """Anti user-enumeration: identical error for a nonexistent account."""
        await make_admin(service)
        with pytest.raises(AuthError, match=GENERIC_LOGIN_ERROR):
            await service.login("naoexiste@amp.local", PASSWORD)

    async def test_nonexistent_path_uses_constant_hash(self):
        """Timing anti-enumeration: a nonexistent email does ONE verification
        against a constant hash (no new hash generated). Ensures the dummy hash
        is a valid bcrypt and that verify returns False without raising."""
        from app.core import security

        assert security.DUMMY_PASSWORD_HASH.startswith("$2")
        assert security.verify_password("qualquer-senha", security.DUMMY_PASSWORD_HASH) is False

    async def test_lockout_incremental(self, service, audit):
        await make_admin(service)
        for _ in range(3):  # login_max_attempts=3
            with pytest.raises(AuthError):
                await service.login(EMAIL, "senha-errada-123")
        # Account locked: even the CORRECT password is rejected
        with pytest.raises(AccountLockedError):
            await service.login(EMAIL, PASSWORD)
        assert audit.has("login_locked")

    async def test_login_ok_resets_counter(self, service):
        await make_admin(service)
        for _ in range(2):
            with pytest.raises(AuthError):
                await service.login(EMAIL, "senha-errada-123")
        user, _ = await service.login(EMAIL, PASSWORD)
        assert user.failed_logins == 0
        assert user.locked_until is None


class TestRole:
    async def test_admin_promotes_member(self, service):
        admin, _ = await make_admin(service)
        invite = await service.create_invite(admin)
        member, _ = await service.register(invite.code, "dev@amp.local", "Dev", PASSWORD)
        updated = await service.set_role(admin, member.id, "admin")
        assert updated.role == "admin"

    async def test_member_does_not_change_role(self, service):
        admin, _ = await make_admin(service)
        invite = await service.create_invite(admin)
        member, _ = await service.register(invite.code, "dev@amp.local", "Dev", PASSWORD)
        with pytest.raises(PermissionDeniedError):
            await service.set_role(member, admin.id, "member")

    async def test_does_not_demote_the_last_admin(self, service):
        admin, _ = await make_admin(service)
        with pytest.raises(ConflictError):
            await service.set_role(admin, admin.id, "member")

    async def test_demotes_admin_when_another_exists(self, service):
        admin, _ = await make_admin(service)
        invite = await service.create_invite(admin)
        member, _ = await service.register(invite.code, "dev@amp.local", "Dev", PASSWORD)
        await service.set_role(admin, member.id, "admin")  # now there are 2 admins
        demoted = await service.set_role(admin, admin.id, "member")  # demotes itself
        assert demoted.role == "member"

    async def test_nonexistent_user(self, service):
        from app.services.errors import NotFoundError

        admin, _ = await make_admin(service)
        with pytest.raises(NotFoundError):
            await service.set_role(admin, 999, "admin")


class TestProfile:
    async def test_update_profile_changes_name_and_audits(self, service, audit):
        user, _ = await make_admin(service)
        updated = await service.update_profile(user, "Julio Barbosa")
        assert updated.name == "Julio Barbosa"
        assert audit.has("profile_updated")


class TestToken:
    async def test_invalid_token_returns_none(self, service):
        await make_admin(service)
        assert await service.get_user_by_token("token-falso") is None

    async def test_token_from_another_secret_returns_none(self, service):
        from app.core.security import create_jwt

        await make_admin(service)
        forged = create_jwt(1, "outro-secret-tambem-com-32-bytes!", 7)
        assert await service.get_user_by_token(forged) is None
