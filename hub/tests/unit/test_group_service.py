import pytest

from app.models.agent import Agent
from app.models.user import User
from app.schemas.group import GroupCreate
from app.services.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
)
from app.services.group_service import GroupService
from tests.unit.fakes import FakeAgentRepository, FakeAuditRepository, FakeGroupRepository


def make_user(user_id: int, role: str = "member") -> User:
    user = User(email=f"user{user_id}@example.com", name=f"U{user_id}", password_hash="x")
    user.id = user_id
    user.role = role
    return user


JULIO = make_user(1)
EDUARDO = make_user(2)
ADMIN = make_user(9, role="admin")


@pytest.fixture
def agents() -> FakeAgentRepository:
    return FakeAgentRepository()


@pytest.fixture
def service(agents) -> GroupService:
    return GroupService(groups=FakeGroupRepository(), agents=agents, audit=FakeAuditRepository())


@pytest.fixture(autouse=True)
async def seed_agents(agents):
    await agents.add(Agent(slug="backend-julio", user_id=JULIO.id, display_name="B"))
    await agents.add(Agent(slug="mobile-eduardo", user_id=EDUARDO.id, display_name="M"))
    await agents.add(Agent(slug="frontend-joao", user_id=EDUARDO.id, display_name="F"))


class TestCreate:
    async def test_cria_grupo(self, service):
        group = await service.create(JULIO, GroupCreate(slug="backend-team", display_name="Time"))
        assert group.slug == "backend-team"
        assert group.created_by == JULIO.id

    async def test_slug_all_reservado(self, service):
        with pytest.raises(InvalidInputError):
            await service.create(JULIO, GroupCreate(slug="all", display_name="Todos"))

    async def test_colisao_com_agente(self, service):
        with pytest.raises(ConflictError):
            await service.create(JULIO, GroupCreate(slug="backend-julio", display_name="X"))

    async def test_colisao_com_grupo(self, service):
        await service.create(JULIO, GroupCreate(slug="backend-team", display_name="T"))
        with pytest.raises(ConflictError):
            await service.create(EDUARDO, GroupCreate(slug="backend-team", display_name="T2"))


class TestDelete:
    async def test_criador_remove(self, service):
        await service.create(JULIO, GroupCreate(slug="backend-team", display_name="T"))
        await service.delete(JULIO, "backend-team")
        assert await service.list_with_members() == []

    async def test_terceiro_nao_remove(self, service):
        await service.create(JULIO, GroupCreate(slug="backend-team", display_name="T"))
        with pytest.raises(PermissionDeniedError):
            await service.delete(EDUARDO, "backend-team")

    async def test_admin_remove(self, service):
        await service.create(JULIO, GroupCreate(slug="backend-team", display_name="T"))
        await service.delete(ADMIN, "backend-team")


class TestMembership:
    async def test_dono_adiciona_o_proprio_agente(self, service):
        await service.create(JULIO, GroupCreate(slug="backend-team", display_name="T"))
        await service.add_member(JULIO, "backend-team", "backend-julio")
        [(_, members)] = await service.list_with_members()
        assert members == ["backend-julio"]

    async def test_terceiro_nao_inscreve_agente_alheio(self, service):
        """Opt-in do dono: ninguém inscreve seu agente sem você."""
        await service.create(JULIO, GroupCreate(slug="backend-team", display_name="T"))
        with pytest.raises(PermissionDeniedError):
            await service.add_member(JULIO, "backend-team", "mobile-eduardo")

    async def test_admin_gerencia_qualquer_agente(self, service):
        await service.create(JULIO, GroupCreate(slug="backend-team", display_name="T"))
        await service.add_member(ADMIN, "backend-team", "mobile-eduardo")
        await service.remove_member(ADMIN, "backend-team", "mobile-eduardo")

    async def test_agente_inexistente(self, service):
        await service.create(JULIO, GroupCreate(slug="backend-team", display_name="T"))
        with pytest.raises(NotFoundError):
            await service.add_member(JULIO, "backend-team", "fantasma-x")

    async def test_adicionar_duas_vezes_e_idempotente(self, service):
        await service.create(JULIO, GroupCreate(slug="backend-team", display_name="T"))
        await service.add_member(JULIO, "backend-team", "backend-julio")
        await service.add_member(JULIO, "backend-team", "backend-julio")
        [(_, members)] = await service.list_with_members()
        assert members == ["backend-julio"]


class TestResolve:
    async def test_all_exclui_o_remetente(self, service):
        recipients = await service.resolve_recipients("@all", "backend-julio")
        assert recipients == ["frontend-joao", "mobile-eduardo"]

    async def test_grupo_resolve_membros(self, service):
        await service.create(JULIO, GroupCreate(slug="mobile-team", display_name="M"))
        await service.add_member(EDUARDO, "mobile-team", "mobile-eduardo")
        await service.add_member(EDUARDO, "mobile-team", "frontend-joao")
        recipients = await service.resolve_recipients("@mobile-team", "frontend-joao")
        assert recipients == ["mobile-eduardo"]

    async def test_grupo_inexistente(self, service):
        with pytest.raises(NotFoundError):
            await service.resolve_recipients("@fantasmas", "backend-julio")

    async def test_referencia_sem_arroba(self, service):
        with pytest.raises(InvalidInputError):
            await service.resolve_recipients("all", "backend-julio")
