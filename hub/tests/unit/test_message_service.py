import pytest

from app.models.agent import Agent
from app.models.user import User
from app.services.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
)
from app.services.message_service import MessageService
from tests.conftest import make_settings
from tests.unit.fakes import (
    FakeAgentRepository,
    FakeAuditRepository,
    FakeMessageRepository,
)


def make_user(user_id: int, role: str = "member") -> User:
    user = User(email=f"user{user_id}@amp.local", name=f"U{user_id}", password_hash="x")
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
def audit() -> FakeAuditRepository:
    return FakeAuditRepository()


@pytest.fixture
def service(agents, audit) -> MessageService:
    return MessageService(
        messages=FakeMessageRepository(),
        agents=agents,
        audit=audit,
        settings=make_settings(message_max_body_bytes=100),
    )


@pytest.fixture(autouse=True)
async def seed_agents(agents):
    await agents.add(Agent(slug="backend-julio", user_id=JULIO.id, display_name="B"))
    await agents.add(Agent(slug="mobile-eduardo", user_id=EDUARDO.id, display_name="M"))


class TestSend:
    async def test_envia_e_fica_pendente(self, service):
        msg = await service.send("mobile-eduardo", "backend-julio", "Existe endpoint de reset?")
        assert msg.delivered_at is None
        pending = await service.pending_for("backend-julio")
        assert [m.id for m in pending] == [msg.id]

    async def test_destinatario_inexistente(self, service):
        with pytest.raises(NotFoundError):
            await service.send("backend-julio", "fantasma-x", "olá")

    async def test_corpo_vazio(self, service):
        with pytest.raises(InvalidInputError):
            await service.send("backend-julio", "mobile-eduardo", "   ")

    async def test_corpo_acima_do_limite(self, service):
        with pytest.raises(InvalidInputError):
            await service.send("backend-julio", "mobile-eduardo", "x" * 101)

    async def test_nao_envia_para_si(self, service):
        with pytest.raises(InvalidInputError):
            await service.send("backend-julio", "backend-julio", "eco")


class TestAllowlist:
    async def test_bloqueia_remetente_fora_da_lista(self, service, agents, audit):
        backend = await agents.get("backend-julio")
        backend.allowed_senders = ["frontend-joao"]
        with pytest.raises(PermissionDeniedError):
            await service.send("mobile-eduardo", "backend-julio", "oi")
        assert audit.has("message_blocked_allowlist")

    async def test_permite_remetente_da_lista(self, service, agents):
        backend = await agents.get("backend-julio")
        backend.allowed_senders = ["mobile-eduardo"]
        msg = await service.send("mobile-eduardo", "backend-julio", "oi")
        assert msg.id is not None

    async def test_sem_allowlist_todos_podem(self, service):
        msg = await service.send("mobile-eduardo", "backend-julio", "oi")
        assert msg.id is not None


class TestDelivery:
    async def test_mark_delivered_limpa_pendentes(self, service):
        msg = await service.send("mobile-eduardo", "backend-julio", "oi")
        await service.mark_delivered([msg.id])
        assert await service.pending_for("backend-julio") == []

    async def test_pendente_expirada_nao_entra_no_flush(self, service):
        from datetime import timedelta

        from app.models.user import utcnow

        msg = await service.send("mobile-eduardo", "backend-julio", "antiga")
        msg.expires_at = utcnow() - timedelta(seconds=1)  # simula TTL vencido
        assert await service.pending_for("backend-julio") == []


class TestThreading:
    async def test_mensagem_raiz_inicia_a_propria_thread(self, service):
        msg = await service.send("mobile-eduardo", "backend-julio", "pergunta")
        assert msg.thread_id == msg.id
        assert msg.in_reply_to is None
        assert msg.type == "request"
        assert msg.priority == "normal"

    async def test_resposta_herda_a_thread(self, service):
        root = await service.send("mobile-eduardo", "backend-julio", "pergunta")
        reply = await service.send(
            "backend-julio", "mobile-eduardo", "resposta", type="response", in_reply_to=root.id
        )
        followup = await service.send(
            "mobile-eduardo", "backend-julio", "mais uma", in_reply_to=reply.id
        )
        assert reply.thread_id == root.id
        assert followup.thread_id == root.id
        assert followup.in_reply_to == reply.id

    async def test_in_reply_to_de_outra_conversa_rejeitado(self, service, agents):
        from app.models.agent import Agent

        await agents.add(Agent(slug="frontend-joao", user_id=5, display_name="F"))
        outra = await service.send("frontend-joao", "backend-julio", "conversa paralela")
        with pytest.raises(InvalidInputError):
            await service.send(
                "mobile-eduardo", "backend-julio", "cross-thread", in_reply_to=outra.id
            )

    async def test_in_reply_to_inexistente_rejeitado(self, service):
        with pytest.raises(InvalidInputError):
            await service.send("mobile-eduardo", "backend-julio", "oi", in_reply_to=999)

    async def test_expires_at_definido_pelo_ttl(self, service):
        msg = await service.send("mobile-eduardo", "backend-julio", "oi")
        assert msg.expires_at is not None


class TestBroadcast:
    async def test_fan_out_cria_uma_dm_por_destinatario(self, service, agents):
        await agents.add(Agent(slug="frontend-joao", user_id=5, display_name="F"))
        sent, skipped = await service.send_broadcast(
            "backend-julio",
            "@all",
            ["mobile-eduardo", "frontend-joao"],
            "anúncio!",
            type="notification",
        )
        assert [m.to_agent for m in sent] == ["mobile-eduardo", "frontend-joao"]
        assert skipped == []
        assert all(m.group_slug == "@all" for m in sent)
        assert all(m.type == "notification" for m in sent)

    async def test_allowlist_do_destinatario_vence_o_broadcast(self, service, agents):
        backend = await agents.get("backend-julio")
        backend.allowed_senders = ["frontend-joao"]  # mobile-eduardo não pode
        sent, skipped = await service.send_broadcast(
            "mobile-eduardo", "@all", ["backend-julio"], "oi time"
        )
        assert sent == []
        assert skipped == ["backend-julio"]

    async def test_broadcast_sem_destinatarios_e_erro(self, service):
        with pytest.raises(InvalidInputError):
            await service.send_broadcast("backend-julio", "@vazio", [], "eco")


class TestHistory:
    async def test_dono_ve_conversa_do_proprio_agente(self, service):
        await service.send("mobile-eduardo", "backend-julio", "pergunta")
        await service.send("backend-julio", "mobile-eduardo", "resposta")
        messages = await service.conversation(JULIO, "backend-julio", "mobile-eduardo")
        assert len(messages) == 2
        assert messages[0].body == "resposta"  # mais recente primeiro

    async def test_terceiro_nao_ve_conversa(self, service):
        intruso = make_user(5)
        await service.send("mobile-eduardo", "backend-julio", "privado")
        with pytest.raises(PermissionDeniedError):
            await service.conversation(intruso, "backend-julio", "mobile-eduardo")

    async def test_admin_ve_tudo(self, service):
        await service.send("mobile-eduardo", "backend-julio", "privado")
        messages = await service.conversation(ADMIN, "backend-julio", "mobile-eduardo")
        assert len(messages) == 1

    async def test_partners_agrupa_com_ultima_mensagem(self, service, agents):
        await agents.add(Agent(slug="frontend-joao", user_id=5, display_name="F"))
        await service.send("mobile-eduardo", "backend-julio", "primeira")
        await service.send("mobile-eduardo", "backend-julio", "segunda")
        await service.send("frontend-joao", "backend-julio", "outra conversa")
        partners = await service.partners(JULIO, "backend-julio")
        by_agent = {p.agent: p.last_message.body for p in partners}
        assert by_agent == {"mobile-eduardo": "segunda", "frontend-joao": "outra conversa"}
