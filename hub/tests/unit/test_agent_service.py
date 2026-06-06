import pytest

from app.core.security import AGENT_KEY_PREFIX
from app.models.user import User
from app.schemas.agent import AgentCreate, AgentSettingsUpdate
from app.services.agent_service import AgentService
from app.services.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
)
from tests.unit.fakes import FakeAgentRepository, FakeAuditRepository


def make_user(user_id: int, role: str = "member") -> User:
    user = User(email=f"user{user_id}@amp.local", name=f"User {user_id}", password_hash="x")
    user.id = user_id
    user.role = role
    return user


@pytest.fixture
def audit() -> FakeAuditRepository:
    return FakeAuditRepository()


@pytest.fixture
def service(audit) -> AgentService:
    return AgentService(agents=FakeAgentRepository(), audit=audit)


OWNER = make_user(1)
OTHER = make_user(2)
ADMIN = make_user(3, role="admin")


class TestCreate:
    async def test_cria_com_defaults_seguros(self, service):
        agent = await service.create(OWNER, AgentCreate(slug="backend-julio", display_name="Backend"))
        assert agent.mode == "inbox"  # nunca nasce em auto (Ameaça 1)
        assert agent.allowed_senders is None
        assert agent.user_id == OWNER.id

    async def test_slug_duplicado(self, service):
        await service.create(OWNER, AgentCreate(slug="backend-julio", display_name="B"))
        with pytest.raises(ConflictError):
            await service.create(OTHER, AgentCreate(slug="backend-julio", display_name="C"))

    async def test_slug_invalido_rejeitado_no_service(self, service):
        # model_construct burla a validação do schema — service revalida
        bad = AgentCreate.model_construct(slug="Backend Julio!", display_name="B")
        with pytest.raises(InvalidInputError):
            await service.create(OWNER, bad)


class TestOwnership:
    async def test_dono_acessa(self, service):
        await service.create(OWNER, AgentCreate(slug="backend-julio", display_name="B"))
        agent = await service.get_owned(OWNER, "backend-julio")
        assert agent.slug == "backend-julio"

    async def test_terceiro_nao_acessa(self, service):
        await service.create(OWNER, AgentCreate(slug="backend-julio", display_name="B"))
        with pytest.raises(PermissionDeniedError):
            await service.get_owned(OTHER, "backend-julio")

    async def test_admin_acessa(self, service):
        await service.create(OWNER, AgentCreate(slug="backend-julio", display_name="B"))
        agent = await service.get_owned(ADMIN, "backend-julio")
        assert agent.slug == "backend-julio"

    async def test_inexistente(self, service):
        with pytest.raises(NotFoundError):
            await service.get_owned(OWNER, "fantasma-x")


class TestSettings:
    async def test_patch_parcial(self, service):
        await service.create(OWNER, AgentCreate(slug="backend-julio", display_name="B"))
        agent = await service.update_settings(
            OWNER, "backend-julio", AgentSettingsUpdate(mode="auto", max_auto_per_hour=5)
        )
        assert agent.mode == "auto"
        assert agent.max_auto_per_hour == 5
        assert agent.auto_timeout_secs == 120  # não tocado

    async def test_allowlist_com_slug_invalido(self, service):
        await service.create(OWNER, AgentCreate(slug="backend-julio", display_name="B"))
        with pytest.raises(InvalidInputError):
            await service.update_settings(
                OWNER,
                "backend-julio",
                AgentSettingsUpdate(allowed_senders=["ok-agent", "INVÁLIDO!"]),
            )

    async def test_clear_allowlist(self, service):
        await service.create(OWNER, AgentCreate(slug="backend-julio", display_name="B"))
        await service.update_settings(
            OWNER, "backend-julio", AgentSettingsUpdate(allowed_senders=["mobile-eduardo"])
        )
        agent = await service.update_settings(
            OWNER, "backend-julio", AgentSettingsUpdate(clear_allowed_senders=True)
        )
        assert agent.allowed_senders is None

    async def test_settings_changed_auditado_sem_conteudo(self, service, audit):
        await service.create(OWNER, AgentCreate(slug="backend-julio", display_name="B"))
        await service.update_settings(
            OWNER, "backend-julio", AgentSettingsUpdate(instructions="segredo interno")
        )
        event = next(e for e in audit.events if e[0] == "settings_changed")
        assert "segredo interno" not in str(event[2])  # conteúdo não vaza pro audit


class TestKeys:
    async def test_cria_e_autentica(self, service):
        await service.create(OWNER, AgentCreate(slug="backend-julio", display_name="B"))
        key, plaintext = await service.create_key(OWNER, "backend-julio", "notebook")
        assert plaintext.startswith(AGENT_KEY_PREFIX)
        agent = await service.authenticate_key("backend-julio", plaintext)
        assert agent is not None and agent.slug == "backend-julio"

    async def test_plaintext_nunca_no_repositorio(self, service):
        await service.create(OWNER, AgentCreate(slug="backend-julio", display_name="B"))
        _, plaintext = await service.create_key(OWNER, "backend-julio")
        keys = await service.list_keys(OWNER, "backend-julio")
        assert all(plaintext not in (k.key_hash, k.label) for k in keys)

    async def test_chave_errada(self, service):
        await service.create(OWNER, AgentCreate(slug="backend-julio", display_name="B"))
        await service.create_key(OWNER, "backend-julio")
        assert await service.authenticate_key("backend-julio", "amp_chave_falsa") is None

    async def test_chave_revogada_nao_autentica(self, service):
        await service.create(OWNER, AgentCreate(slug="backend-julio", display_name="B"))
        key, plaintext = await service.create_key(OWNER, "backend-julio")
        await service.revoke_key(OWNER, "backend-julio", key.id)
        assert await service.authenticate_key("backend-julio", plaintext) is None

    async def test_chave_nao_autentica_outro_slug(self, service):
        """Chave válida de A não serve para se passar por B."""
        await service.create(OWNER, AgentCreate(slug="backend-julio", display_name="B"))
        await service.create(OWNER, AgentCreate(slug="infra-julio", display_name="I"))
        _, plaintext = await service.create_key(OWNER, "backend-julio")
        assert await service.authenticate_key("infra-julio", plaintext) is None

    async def test_terceiro_nao_cria_chave(self, service):
        await service.create(OWNER, AgentCreate(slug="backend-julio", display_name="B"))
        with pytest.raises(PermissionDeniedError):
            await service.create_key(OTHER, "backend-julio")
