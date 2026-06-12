"""Approval decision flow (Epic 03 · 3.3): approve sends as the agent, edit
sends the edited body, reject sends nothing, and a decided approval is final."""

from datetime import timedelta

import pytest

from app.models.agent import Agent
from app.models.approval import Approval
from app.models.message import Message
from app.models.user import User, utcnow
from app.services.approval_service import ApprovalService
from app.services.errors import InvalidInputError, NotFoundError, PermissionDeniedError
from tests.unit.fakes import (
    FakeAgentRepository,
    FakeApprovalRepository,
    FakeAuditRepository,
)


def make_user(uid: int, role: str = "member") -> User:
    u = User(email=f"u{uid}@amp.local", name=f"U{uid}", password_hash="x")
    u.id = uid
    u.role = role
    return u


class _Sender:
    """Records the send-as-agent calls and returns a stub Message."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, int | None]] = []

    async def __call__(self, from_slug, to_slug, body, in_reply_to) -> Message:
        self.calls.append((from_slug, to_slug, body, in_reply_to))
        msg = Message(from_agent=from_slug, to_agent=to_slug, body=body)
        msg.id = 999
        return msg


async def _setup(sender=None):
    approvals = FakeApprovalRepository()
    agents = FakeAgentRepository()
    audit = FakeAuditRepository()
    owner = make_user(1)
    await agents.add(Agent(slug="backend-julio", user_id=owner.id, display_name="B"))
    svc = ApprovalService(approvals, agents, audit, sender=sender)
    approval = await approvals.add(
        Approval(
            agent_slug="backend-julio",
            to_agent="mobile-eduardo",
            draft_body="Sim: POST /api/v1/auth/password-reset",
            trigger_message_id=42,
        )
    )
    return svc, approvals, audit, owner, approval


class TestDecide:
    async def test_approve_sends_the_draft_as_the_agent(self):
        sender = _Sender()
        svc, approvals, audit, owner, approval = await _setup(sender)
        decided, msg = await svc.decide(owner, approval.id, "approve")
        assert decided.status == "approved"
        assert decided.decided_by == owner.id and decided.decided_at is not None
        assert sender.calls == [("backend-julio", "mobile-eduardo", approval.draft_body, 42)]
        assert msg is not None and msg.id == 999
        assert audit.has("approval_decided")

    async def test_edit_sends_the_edited_body_and_marks_edited(self):
        sender = _Sender()
        svc, _a, _au, owner, approval = await _setup(sender)
        decided, _msg = await svc.decide(owner, approval.id, "approve", body="resposta revisada")
        assert decided.status == "edited"
        assert sender.calls[0][2] == "resposta revisada"

    async def test_reject_sends_nothing(self):
        sender = _Sender()
        svc, _a, _au, owner, approval = await _setup(sender)
        decided, msg = await svc.decide(owner, approval.id, "reject")
        assert decided.status == "rejected"
        assert msg is None
        assert sender.calls == []

    async def test_a_decided_approval_is_final(self):
        sender = _Sender()
        svc, _a, _au, owner, approval = await _setup(sender)
        await svc.decide(owner, approval.id, "approve")
        with pytest.raises(InvalidInputError):
            await svc.decide(owner, approval.id, "reject")

    async def test_missing_approval_is_not_found(self):
        svc, *_ = await _setup(_Sender())
        with pytest.raises(NotFoundError):
            await svc.decide(make_user(1), 12345, "approve")

    async def test_non_owner_cannot_decide(self):
        sender = _Sender()
        svc, _a, _au, _owner, approval = await _setup(sender)
        with pytest.raises(PermissionDeniedError):
            await svc.decide(make_user(2), approval.id, "approve")
        assert sender.calls == []


class TestExpiry:
    async def test_expire_pending_auto_rejects_stale_only(self):
        approvals = FakeApprovalRepository()
        agents = FakeAgentRepository()
        audit = FakeAuditRepository()
        svc = ApprovalService(approvals, agents, audit)
        old = await approvals.add(Approval(agent_slug="a", to_agent="b", draft_body="x"))
        await approvals.add(Approval(agent_slug="a", to_agent="b", draft_body="y"))  # fresh
        old.created_at = utcnow() - timedelta(hours=72)
        await approvals.save(old)

        assert await svc.expire_pending(48) == 1
        assert (await approvals.get(old.id)).status == "rejected"
        assert await svc.expire_pending(0) == 0  # disabled
