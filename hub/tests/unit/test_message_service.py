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
    async def test_sends_and_stays_pending(self, service):
        msg = await service.send("mobile-eduardo", "backend-julio", "Existe endpoint de reset?")
        assert msg.delivered_at is None
        pending = await service.pending_for("backend-julio")
        assert [m.id for m in pending] == [msg.id]

    async def test_nonexistent_recipient(self, service):
        with pytest.raises(NotFoundError):
            await service.send("backend-julio", "fantasma-x", "olá")

    async def test_empty_body(self, service):
        with pytest.raises(InvalidInputError):
            await service.send("backend-julio", "mobile-eduardo", "   ")

    async def test_body_over_the_limit(self, service):
        with pytest.raises(InvalidInputError):
            await service.send("backend-julio", "mobile-eduardo", "x" * 101)

    async def test_does_not_send_to_self(self, service):
        with pytest.raises(InvalidInputError):
            await service.send("backend-julio", "backend-julio", "eco")


class TestSendAudit:
    """Only security-weight sends hit the audit log (option C): an alert or a
    cross-owner message. Routine same-owner DMs are not audited (the `messages`
    table is their record)."""

    async def test_cross_owner_send_is_audited(self, service, audit):
        # backend-julio (owner 1) → mobile-eduardo (owner 2): crosses ownership
        await service.send("backend-julio", "mobile-eduardo", "oi")
        assert audit.has("message_sent")

    async def test_same_owner_routine_dm_is_not_audited(self, service, agents, audit):
        await agents.add(Agent(slug="api-julio", user_id=JULIO.id, display_name="A"))
        await service.send("backend-julio", "api-julio", "status?")  # same owner, type=request
        assert not audit.has("message_sent")

    async def test_alert_is_audited_even_same_owner(self, service, agents, audit):
        await agents.add(Agent(slug="api-julio", user_id=JULIO.id, display_name="A"))
        await service.send("backend-julio", "api-julio", "caiu!", type="alert")
        assert audit.has("message_sent")

    async def test_broadcast_member_send_is_not_double_audited(self, service, audit):
        # a fan-out message carries group_slug → covered by broadcast_sent, not message_sent
        await service.send("backend-julio", "mobile-eduardo", "aviso", group="@all")
        assert not audit.has("message_sent")


class TestAllowlist:
    async def test_blocks_sender_not_in_the_list(self, service, agents, audit):
        backend = await agents.get("backend-julio")
        backend.allowed_senders = ["frontend-joao"]
        with pytest.raises(PermissionDeniedError):
            await service.send("mobile-eduardo", "backend-julio", "oi")
        assert audit.has("message_blocked_allowlist")

    async def test_allows_sender_in_the_list(self, service, agents):
        backend = await agents.get("backend-julio")
        backend.allowed_senders = ["mobile-eduardo"]
        msg = await service.send("mobile-eduardo", "backend-julio", "oi")
        assert msg.id is not None

    async def test_without_allowlist_everyone_can(self, service):
        msg = await service.send("mobile-eduardo", "backend-julio", "oi")
        assert msg.id is not None


class TestDelivery:
    async def test_mark_delivered_clears_pending(self, service):
        msg = await service.send("mobile-eduardo", "backend-julio", "oi")
        await service.mark_delivered([msg.id])
        assert await service.pending_for("backend-julio") == []

    async def test_expired_pending_excluded_from_flush(self, service):
        from datetime import timedelta

        from app.models.user import utcnow

        msg = await service.send("mobile-eduardo", "backend-julio", "antiga")
        msg.expires_at = utcnow() - timedelta(seconds=1)  # simulates an expired TTL
        assert await service.pending_for("backend-julio") == []


class TestThreading:
    async def test_root_message_starts_its_own_thread(self, service):
        msg = await service.send("mobile-eduardo", "backend-julio", "pergunta")
        assert msg.thread_id == msg.id
        assert msg.in_reply_to is None
        assert msg.type == "request"
        assert msg.priority == "normal"

    async def test_reply_inherits_the_thread(self, service):
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

    async def test_in_reply_to_from_another_conversation_rejected(self, service, agents):
        from app.models.agent import Agent

        await agents.add(Agent(slug="frontend-joao", user_id=5, display_name="F"))
        outra = await service.send("frontend-joao", "backend-julio", "conversa paralela")
        with pytest.raises(InvalidInputError):
            await service.send(
                "mobile-eduardo", "backend-julio", "cross-thread", in_reply_to=outra.id
            )

    async def test_nonexistent_in_reply_to_rejected(self, service):
        with pytest.raises(InvalidInputError):
            await service.send("mobile-eduardo", "backend-julio", "oi", in_reply_to=999)

    async def test_expires_at_set_by_the_ttl(self, service):
        msg = await service.send("mobile-eduardo", "backend-julio", "oi")
        assert msg.expires_at is not None


class TestBroadcast:
    async def test_fan_out_creates_one_dm_per_recipient(self, service, agents):
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

    async def test_recipient_allowlist_wins_over_broadcast(self, service, agents):
        backend = await agents.get("backend-julio")
        backend.allowed_senders = ["frontend-joao"]  # mobile-eduardo cannot
        sent, skipped = await service.send_broadcast(
            "mobile-eduardo", "@all", ["backend-julio"], "oi time"
        )
        assert sent == []
        assert skipped == ["backend-julio"]

    async def test_broadcast_without_recipients_is_error(self, service):
        with pytest.raises(InvalidInputError):
            await service.send_broadcast("backend-julio", "@vazio", [], "eco")


class TestHistory:
    async def test_owner_sees_their_own_agents_conversation(self, service):
        await service.send("mobile-eduardo", "backend-julio", "pergunta")
        await service.send("backend-julio", "mobile-eduardo", "resposta")
        messages = await service.conversation(JULIO, "backend-julio", "mobile-eduardo")
        assert len(messages) == 2
        assert messages[0].body == "resposta"  # most recent first

    async def test_third_party_does_not_see_conversation(self, service):
        intruso = make_user(5)
        await service.send("mobile-eduardo", "backend-julio", "privado")
        with pytest.raises(PermissionDeniedError):
            await service.conversation(intruso, "backend-julio", "mobile-eduardo")

    async def test_admin_sees_everything(self, service):
        await service.send("mobile-eduardo", "backend-julio", "privado")
        messages = await service.conversation(ADMIN, "backend-julio", "mobile-eduardo")
        assert len(messages) == 1

    async def test_partners_groups_by_last_message(self, service, agents):
        await agents.add(Agent(slug="frontend-joao", user_id=5, display_name="F"))
        await service.send("mobile-eduardo", "backend-julio", "primeira")
        await service.send("mobile-eduardo", "backend-julio", "segunda")
        await service.send("frontend-joao", "backend-julio", "outra conversa")
        partners = await service.partners(JULIO, "backend-julio")
        by_agent = {p.agent: p.last_message.body for p in partners}
        assert by_agent == {"mobile-eduardo": "segunda", "frontend-joao": "outra conversa"}
