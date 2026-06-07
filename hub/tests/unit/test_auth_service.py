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
    async def test_needs_setup_apenas_sem_usuarios(self, service):
        assert await service.needs_setup() is True
        await make_admin(service)
        assert await service.needs_setup() is False

    async def test_primeiro_usuario_vira_admin(self, service):
        user, token = await make_admin(service)
        assert user.role == "admin"
        assert token
        assert (await service.get_user_by_token(token)).id == user.id

    async def test_setup_segunda_vez_falha(self, service):
        await make_admin(service)
        with pytest.raises(ConflictError):
            await service.setup_admin("outro@amp.local", "Outro", PASSWORD)


class TestRegister:
    async def test_registro_com_convite_valido(self, service):
        admin, _ = await make_admin(service)
        invite = await service.create_invite(admin)
        user, token = await service.register(
            invite.code, "dev@amp.local", "Dev", "senha-do-dev-123"
        )
        assert user.role == "member"
        assert invite.used_by == user.id
        assert token

    async def test_convite_inexistente(self, service):
        with pytest.raises(PermissionDeniedError):
            await service.register("AMP-XXXX-XXXX-XXXX-XXXX", "a@b.c", "A", PASSWORD)

    async def test_convite_expirado(self, service):
        admin, _ = await make_admin(service)
        invite = await service.create_invite(admin)
        invite.expires_at = utcnow() - timedelta(hours=1)
        with pytest.raises(PermissionDeniedError):
            await service.register(invite.code, "a@b.c", "A", PASSWORD)

    async def test_convite_de_uso_unico(self, service):
        admin, _ = await make_admin(service)
        invite = await service.create_invite(admin)
        await service.register(invite.code, "dev@amp.local", "Dev", PASSWORD)
        with pytest.raises(PermissionDeniedError):
            await service.register(invite.code, "dev2@amp.local", "Dev2", PASSWORD)

    async def test_email_duplicado(self, service):
        admin, _ = await make_admin(service)
        invite = await service.create_invite(admin)
        with pytest.raises(ConflictError):
            await service.register(invite.code, EMAIL, "Clone", PASSWORD)

    async def test_member_nao_gera_convite(self, service):
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

    async def test_senha_errada_mensagem_generica(self, service):
        await make_admin(service)
        with pytest.raises(AuthError, match=GENERIC_LOGIN_ERROR):
            await service.login(EMAIL, "senha-errada-123")

    async def test_email_inexistente_mesma_mensagem_generica(self, service):
        """Anti user-enumeration: erro idêntico para conta inexistente."""
        await make_admin(service)
        with pytest.raises(AuthError, match=GENERIC_LOGIN_ERROR):
            await service.login("naoexiste@amp.local", PASSWORD)

    async def test_caminho_inexistente_usa_hash_constante(self):
        """Timing anti-enumeration: e-mail inexistente faz UMA verificação
        contra hash constante (não gera hash novo). Garante que o dummy hash
        é um bcrypt válido e que verify retorna False sem levantar."""
        from app.core import security

        assert security.DUMMY_PASSWORD_HASH.startswith("$2")
        assert security.verify_password("qualquer-senha", security.DUMMY_PASSWORD_HASH) is False

    async def test_lockout_incremental(self, service, audit):
        await make_admin(service)
        for _ in range(3):  # login_max_attempts=3
            with pytest.raises(AuthError):
                await service.login(EMAIL, "senha-errada-123")
        # Conta bloqueada: até a senha CORRETA é rejeitada
        with pytest.raises(AccountLockedError):
            await service.login(EMAIL, PASSWORD)
        assert audit.has("login_locked")

    async def test_login_ok_zera_contador(self, service):
        await make_admin(service)
        for _ in range(2):
            with pytest.raises(AuthError):
                await service.login(EMAIL, "senha-errada-123")
        user, _ = await service.login(EMAIL, PASSWORD)
        assert user.failed_logins == 0
        assert user.locked_until is None


class TestToken:
    async def test_token_invalido_retorna_none(self, service):
        await make_admin(service)
        assert await service.get_user_by_token("token-falso") is None

    async def test_token_de_outro_secret_retorna_none(self, service):
        from app.core.security import create_jwt

        await make_admin(service)
        forged = create_jwt(1, "outro-secret-tambem-com-32-bytes!", 7)
        assert await service.get_user_by_token(forged) is None
