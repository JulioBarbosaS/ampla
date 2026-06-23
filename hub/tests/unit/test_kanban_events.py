"""Opt-in event cards (Epic 06 · 6.5/#1): a delegation/escalation drops a card on
the target owner's board that enabled the flag — off by default. Resolution is
tested against a real KanbanService; the delegation/escalation wiring is tested
with a recording stub so it stays isolated from the ordering machinery."""

import pytest

from app.models.agent import Agent
from app.models.message import Message
from app.models.user import User
from app.schemas.kanban import BoardCreate, BoardUpdate, CardCreate
from app.schemas.ws import AutorespondRecord
from app.services.autorespond_service import AutorespondService
from app.services.delegation_service import DelegationService
from app.services.errors import InvalidInputError
from app.services.kanban_service import KanbanService
from app.services.notification_service import NotificationService
from tests.unit.fakes import (
    FakeAgentRepository,
    FakeAuditRepository,
    FakeAutorespondRunRepository,
    FakeDelegationRepository,
    FakeKanbanRepository,
    FakeNotificationRepository,
    FakeUserRepository,
)


class TestEventCardResolution:
    async def _service(self):
        boards = FakeKanbanRepository()
        users = FakeUserRepository()
        owner = await users.add(User(email="o@amp.local", name="O", password_hash="x"))
        svc = KanbanService(boards=boards, audit=FakeAuditRepository())
        return svc, owner

    async def test_creates_a_card_on_the_flagged_board(self):
        svc, owner = await self._service()
        board = await svc.create_board(owner, BoardCreate(name="Tarefas"))
        await svc.update_board(owner, board.id, BoardUpdate(auto_card_on_delegation=True))
        card = await svc.create_card_for_event(
            owner_id=owner.id,
            flag=KanbanService.DELEGATION_FLAG,
            title="Revisar login",
            body="contexto",
            assignee="mobile-eduardo",
            origin={"kind": "delegation", "id": 7},
        )
        assert card is not None
        assert card.board_id == board.id
        assert card.assignee == "mobile-eduardo"
        assert card.origin == {"kind": "delegation", "id": 7}
        # landed in the board's landing column
        _, columns, _ = await svc.get_board_full(owner, board.id)
        assert card.column_id == next(c.id for c in columns if c.is_landing)

    async def test_no_flagged_board_creates_nothing(self):
        svc, owner = await self._service()
        await svc.create_board(owner, BoardCreate(name="Sem flag"))  # flag off (default)
        card = await svc.create_card_for_event(
            owner_id=owner.id,
            flag=KanbanService.DELEGATION_FLAG,
            title="x",
            body="",
            assignee=None,
            origin={"kind": "delegation", "id": 1},
        )
        assert card is None

    async def test_invalid_flag_rejected(self):
        svc, owner = await self._service()
        with pytest.raises(InvalidInputError):
            await svc.create_card_for_event(
                owner_id=owner.id,
                flag="auto_card_on_anything",
                title="x",
                body="",
                assignee=None,
                origin={},
            )


class TestEventCardLifecycle:
    """Epic 07: when the event a card came from finishes, the hub moves the card
    to the board's Done column — respecting the dependency gate, idempotently."""

    async def _board_with_event_card(self):
        boards = FakeKanbanRepository()
        users = FakeUserRepository()
        owner = await users.add(User(email="o@amp.local", name="O", password_hash="x"))
        svc = KanbanService(boards=boards, audit=FakeAuditRepository())
        board = await svc.create_board(owner, BoardCreate(name="Tarefas"))
        await svc.update_board(owner, board.id, BoardUpdate(auto_card_on_delegation=True))
        card = await svc.create_card_for_event(
            owner_id=owner.id,
            flag=KanbanService.DELEGATION_FLAG,
            title="Revisar login",
            body="ctx",
            assignee="mobile-eduardo",
            origin={"kind": "delegation", "id": 7},
        )
        return svc, owner, board, card

    async def test_moves_the_card_to_the_done_column(self):
        svc, owner, board, card = await self._board_with_event_card()
        moved = await svc.complete_card_for_event(kind="delegation", ref_id=7)
        assert moved is not None and moved.id == card.id
        _, columns, _ = await svc.get_board_full(owner, board.id)
        done = next(c for c in columns if c.is_done)
        assert moved.column_id == done.id

    async def test_is_idempotent_once_done(self):
        svc, _, _, _ = await self._board_with_event_card()
        await svc.complete_card_for_event(kind="delegation", ref_id=7)
        # a second completion is a no-op (already in a done column)
        assert await svc.complete_card_for_event(kind="delegation", ref_id=7) is None

    async def test_unknown_origin_is_a_noop(self):
        svc, _, _, _ = await self._board_with_event_card()
        assert await svc.complete_card_for_event(kind="delegation", ref_id=999) is None

    async def test_blocked_card_is_not_auto_done(self):
        svc, owner, board, card = await self._board_with_event_card()
        # add an unmet dependency: the card is blocked until `blocker` is done
        blocker = await svc.create_card(owner, board.id, CardCreate(title="pré-requisito"))
        await svc.add_dependency(owner, card.id, blocker.id)
        assert await svc.complete_card_for_event(kind="delegation", ref_id=7) is None
        # still in the landing column, NOT done (Done⇒deps-Done invariant kept)
        reread = await svc.get_card(owner, card.id)
        _, cols, _ = await svc.get_board_full(owner, board.id)
        landing_col = next(c.id for c in cols if c.is_landing)
        assert reread.column_id == landing_col
        # once the blocker reaches Done, the lifecycle move succeeds
        _, columns, _ = await svc.get_board_full(owner, board.id)
        done = next(c for c in columns if c.is_done)
        await svc.move_card(
            owner,
            blocker.id,
            done.id,
            before_id=None,
            after_id=None,
            expected_version=blocker.version,
        )
        moved = await svc.complete_card_for_event(kind="delegation", ref_id=7)
        assert moved is not None and moved.column_id == done.id

    async def test_escalation_card_to_done_records_resolution(self):
        """Epic 07: an escalation card reaching Done IS the resolution (audited)."""
        boards = FakeKanbanRepository()
        users = FakeUserRepository()
        owner = await users.add(User(email="o@amp.local", name="O", password_hash="x"))
        audit = FakeAuditRepository()
        svc = KanbanService(boards=boards, audit=audit)
        board = await svc.create_board(owner, BoardCreate(name="Suporte"))
        await svc.update_board(owner, board.id, BoardUpdate(auto_card_on_escalation=True))
        card = await svc.create_card_for_event(
            owner_id=owner.id,
            flag=KanbanService.ESCALATION_FLAG,
            title="Precisa de humano",
            body="",
            assignee=f"user:{owner.id}",
            origin={"kind": "escalation", "from": "cliente-x"},
            priority="high",
        )
        _, columns, _ = await svc.get_board_full(owner, board.id)
        done = next(c for c in columns if c.is_done)
        await svc.move_card(
            owner,
            card.id,
            done.id,
            before_id=None,
            after_id=None,
            expected_version=card.version,
        )
        assert audit.has("escalation_resolved")
        # a non-escalation card moved to Done does NOT record a resolution
        plain = await svc.create_card(owner, board.id, CardCreate(title="comum"))
        audit.events.clear()
        await svc.move_card(
            owner,
            plain.id,
            done.id,
            before_id=None,
            after_id=None,
            expected_version=plain.version,
        )
        assert not audit.has("escalation_resolved")


class _KanbanStub:
    """Records create_card_for_event calls without touching the board machinery."""

    DELEGATION_FLAG = "auto_card_on_delegation"
    ESCALATION_FLAG = "auto_card_on_escalation"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create_card_for_event(self, **kwargs):
        self.calls.append(kwargs)
        return None


class _Sender:
    def __init__(self) -> None:
        self._seq = 100

    async def __call__(self, from_slug: str, to_slug: str, body: str) -> Message:
        self._seq += 1
        msg = Message(from_agent=from_slug, to_agent=to_slug, body=body, type="task")
        msg.id = self._seq
        return msg


class TestDelegationEventCard:
    async def test_delegation_requests_a_card_for_the_delegate_owner(self):
        agents = FakeAgentRepository()
        await agents.add(Agent(slug="backend-julio", user_id=1, display_name="B"))
        await agents.add(Agent(slug="mobile-eduardo", user_id=2, display_name="M"))  # owner 2
        kanban = _KanbanStub()
        svc = DelegationService(
            FakeDelegationRepository(),
            agents,
            FakeAuditRepository(),
            sender=_Sender(),
            kanban=kanban,
        )
        deleg = await svc.delegate("backend-julio", "mobile-eduardo", "Revisar login", "ctx")
        assert deleg is not None and deleg.status == "open"
        assert len(kanban.calls) == 1
        call = kanban.calls[0]
        assert call["owner_id"] == 2  # the DELEGATE's owner
        assert call["flag"] == _KanbanStub.DELEGATION_FLAG
        assert call["assignee"] == "mobile-eduardo"
        assert call["origin"] == {"kind": "delegation", "id": deleg.id}


class TestEscalationEventCard:
    async def test_escalation_requests_a_card_for_the_agent_owner(self):
        runs = FakeAutorespondRunRepository()
        agents = FakeAgentRepository()
        await agents.add(Agent(slug="backend-julio", user_id=5, display_name="B"))
        users = FakeUserRepository()
        notifications = NotificationService(notifications=FakeNotificationRepository(), users=users)
        kanban = _KanbanStub()
        svc = AutorespondService(runs, agents=agents, notifications=notifications, kanban=kanban)
        # a skipped/escalate run forces escalation regardless of escalate_on
        record = AutorespondRecord(
            trigger_message_id=1, from_sender="mobile-eduardo", result="skipped", reason="escalate"
        )
        await svc.record_run("backend-julio", record)
        assert len(kanban.calls) == 1
        call = kanban.calls[0]
        assert call["owner_id"] == 5  # the escalating agent's owner
        assert call["flag"] == _KanbanStub.ESCALATION_FLAG
        assert call["origin"]["kind"] == "escalation"
