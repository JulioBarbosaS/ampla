"""Agent-to-agent delegation (Epic 04 · 4.4): the delegator hands a task (sent
as a task message, allowlist enforced) and the delegate's in-thread reply closes
the loop."""

import pytest

from app.models.agent import Agent
from app.models.delegation import Delegation
from app.models.message import Message
from app.models.user import User
from app.services.delegation_service import DelegationService
from app.services.errors import InvalidInputError, PermissionDeniedError
from app.services.message_service import MessageService
from app.services.notification_service import NotificationService
from tests.conftest import make_settings
from tests.unit.fakes import (
    FakeAgentRepository,
    FakeAuditRepository,
    FakeDelegationRepository,
    FakeMessageRepository,
    FakeNotificationRepository,
    FakeUserRepository,
)


class _Sender:
    """Records the task-send calls and returns a stub Message (or blocks)."""

    def __init__(self, *, block: bool = False) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self._block = block
        self._seq = 100

    async def __call__(self, from_slug: str, to_slug: str, body: str) -> Message:
        self.calls.append((from_slug, to_slug, body))
        if self._block:
            raise PermissionDeniedError(f"{to_slug!r} não aceita mensagens deste agente.")
        self._seq += 1
        msg = Message(from_agent=from_slug, to_agent=to_slug, body=body, type="task")
        msg.id = self._seq
        return msg


async def _setup(sender):
    delegations = FakeDelegationRepository()
    agents = FakeAgentRepository()
    audit = FakeAuditRepository()
    await agents.add(Agent(slug="backend-julio", user_id=1, display_name="B"))
    svc = DelegationService(delegations, agents, audit, sender=sender)
    return svc, delegations, audit


class TestDelegate:
    async def test_creates_open_delegation_and_sends_the_task(self):
        sender = _Sender()
        svc, delegations, audit = await _setup(sender)
        deleg = await svc.delegate("backend-julio", "mobile-eduardo", "Revisar o login", "contexto")
        assert deleg is not None
        assert deleg.status == "open"
        assert deleg.to_agent == "mobile-eduardo"
        assert deleg.root_message_id == 101  # the sent task message id
        # the task message carries both the task and the (untrusted) context
        assert sender.calls[0][0] == "backend-julio"
        assert "Revisar o login" in sender.calls[0][2]
        assert "contexto" in sender.calls[0][2]
        assert audit.has("delegation_created")

    async def test_allowlist_block_becomes_declined(self):
        sender = _Sender(block=True)
        svc, _delegations, audit = await _setup(sender)
        deleg = await svc.delegate("backend-julio", "mobile-eduardo", "tarefa")
        assert deleg is not None
        assert deleg.status == "declined"
        assert deleg.root_message_id is None
        assert audit.has("delegation_declined")

    async def test_cannot_delegate_to_self(self):
        svc, _d, _a = await _setup(_Sender())
        with pytest.raises(InvalidInputError):
            await svc.delegate("backend-julio", "backend-julio", "tarefa")

    async def test_open_cap_blocks_further_delegations(self):
        sender = _Sender()
        delegations = FakeDelegationRepository()
        agents = FakeAgentRepository()
        await agents.add(Agent(slug="backend-julio", user_id=1, display_name="B"))
        svc = DelegationService(
            delegations, agents, FakeAuditRepository(), sender=sender, max_open=1
        )
        await svc.delegate("backend-julio", "mobile-eduardo", "primeira")
        with pytest.raises(InvalidInputError):
            await svc.delegate("backend-julio", "outro-agente", "segunda")


class TestCompletion:
    """A reply from the delegate, in the delegated thread, completes the row."""

    async def _message_service(self):
        agents = FakeAgentRepository()
        delegations = FakeDelegationRepository()
        notifications = FakeNotificationRepository()
        users = FakeUserRepository()
        owner = await users.add(User(email="o@amp.local", name="O", password_hash="x"))
        await agents.add(Agent(slug="backend-julio", user_id=owner.id, display_name="B"))
        await agents.add(Agent(slug="mobile-eduardo", user_id=owner.id, display_name="M"))
        messages = FakeMessageRepository()
        svc = MessageService(
            messages=messages,
            agents=agents,
            audit=FakeAuditRepository(),
            settings=make_settings(message_max_body_bytes=10_000),
            notifications=NotificationService(notifications=notifications, users=users),
            delegations=delegations,
        )
        return svc, messages, delegations, notifications

    async def test_reply_in_thread_completes_and_notifies(self):
        svc, messages, delegations, notifications = await self._message_service()
        # A delegated B: the task message A→B is the thread root
        task = await messages.add(
            Message(from_agent="backend-julio", to_agent="mobile-eduardo", body="t", type="task")
        )
        deleg = await delegations.add(
            Delegation(
                from_agent="backend-julio",
                to_agent="mobile-eduardo",
                task="t",
                root_message_id=task.id,
                status="open",
            )
        )
        # B replies in-thread → completes the delegation
        await svc.send(
            "mobile-eduardo", "backend-julio", "pronto", type="response", in_reply_to=task.id
        )
        assert (
            await delegations.find_open_for_reply(
                delegator="backend-julio", delegate="mobile-eduardo", root_message_id=task.id
            )
        ) is None  # no longer open
        completed = delegations._items[deleg.id]
        assert completed.status == "completed"
        assert completed.result_message_id is not None
        # the delegator's owner is notified the result came back
        assert any(n.reason == "task_assigned" for n in notifications._items.values())

    async def test_unrelated_reply_does_not_complete(self):
        svc, messages, delegations, _notifications = await self._message_service()
        task = await messages.add(
            Message(from_agent="backend-julio", to_agent="mobile-eduardo", body="t", type="task")
        )
        deleg = await delegations.add(
            Delegation(
                from_agent="backend-julio",
                to_agent="mobile-eduardo",
                task="t",
                root_message_id=task.id,
                status="open",
            )
        )
        # a fresh message (no in_reply_to) does not complete the delegation
        await svc.send("mobile-eduardo", "backend-julio", "oi à toa", type="request")
        assert delegations._items[deleg.id].status == "open"
