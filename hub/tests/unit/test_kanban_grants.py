"""Per-agent, per-board permission model (Epic 06 · 6.3): the capability matrix,
role resolution (grant vs board default), and grant management (owner/admin,
audited, cross-board isolated)."""

import pytest

from app.models.agent import Agent
from app.models.kanban import KanbanCard
from app.models.user import User
from app.schemas.kanban import BoardCreate
from app.services.errors import NotFoundError, PermissionDeniedError
from app.services.kanban_service import KanbanService, agent_capability
from tests.unit.fakes import (
    FakeAgentRepository,
    FakeAuditRepository,
    FakeKanbanRepository,
    FakeUserRepository,
)


async def _setup():
    boards = FakeKanbanRepository()
    audit = FakeAuditRepository()
    agents = FakeAgentRepository()
    users = FakeUserRepository()
    owner = await users.add(User(email="owner@amp.local", name="Owner", password_hash="x"))
    await agents.add(Agent(slug="backend-ana", user_id=owner.id, display_name="Ana"))
    svc = KanbanService(boards=boards, audit=audit, agents=agents)
    return svc, boards, audit, users, owner


class TestCapabilityMatrix:
    def test_none_role_denies_everything(self):
        for action in ("view", "comment", "create", "move", "edit", "delete", "manage_columns"):
            assert agent_capability("none", action) is False
            assert agent_capability("none", action, owns_card=True) is False

    def test_viewer_reads_and_comments_only(self):
        assert agent_capability("viewer", "view")
        assert agent_capability("viewer", "comment")
        for action in ("create", "move", "edit", "delete", "manage_columns"):
            assert agent_capability("viewer", action) is False

    def test_contributor_creates_and_touches_only_its_own(self):
        assert agent_capability("contributor", "create")
        assert agent_capability("contributor", "comment")
        # own/assigned card: yes; others': no
        assert agent_capability("contributor", "move", owns_card=True)
        assert agent_capability("contributor", "edit", owns_card=True)
        assert agent_capability("contributor", "move", owns_card=False) is False
        assert agent_capability("contributor", "edit", owns_card=False) is False
        # never delete or manage columns
        assert agent_capability("contributor", "delete", owns_card=True) is False
        assert agent_capability("contributor", "manage_columns") is False

    def test_editor_can_do_everything_to_any_card(self):
        for action in ("view", "comment", "create", "move", "edit", "delete", "manage_columns"):
            assert agent_capability("editor", action, owns_card=False)


class TestOwnership:
    def test_owns_card_when_created_or_assigned(self):
        created = KanbanCard(board_id=1, column_id=1, rank="m", title="t", created_by="backend-ana")
        assigned = KanbanCard(
            board_id=1,
            column_id=1,
            rank="m",
            title="t",
            created_by="user:1",
            assignee="backend-ana",
        )
        other = KanbanCard(board_id=1, column_id=1, rank="m", title="t", created_by="user:1")
        assert KanbanService._agent_owns(created, "backend-ana")
        assert KanbanService._agent_owns(assigned, "backend-ana")
        assert KanbanService._agent_owns(other, "backend-ana") is False


class TestRoleResolution:
    async def test_grant_overrides_board_default(self):
        svc, _boards, _audit, _users, owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B", default_agent_role="viewer"))
        # no grant → board default
        assert await svc.agent_role(board, "backend-ana") == "viewer"
        # an explicit grant wins
        await svc.set_grant(owner, board.id, "backend-ana", "editor")
        assert await svc.agent_role(board, "backend-ana") == "editor"

    async def test_dev_only_board_default_is_none(self):
        svc, _boards, _audit, _users, owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))  # default_agent_role=none
        assert await svc.agent_role(board, "backend-ana") == "none"

    async def test_grant_does_not_leak_across_boards(self):
        svc, _boards, _audit, _users, owner = await _setup()
        a = await svc.create_board(owner, BoardCreate(name="A"))
        b = await svc.create_board(owner, BoardCreate(name="B"))
        await svc.set_grant(owner, a.id, "backend-ana", "editor")
        assert await svc.agent_role(a, "backend-ana") == "editor"
        assert await svc.agent_role(b, "backend-ana") == "none"  # board B untouched


class TestGrantManagement:
    async def test_set_and_remove_grant_are_audited(self):
        svc, _boards, audit, _users, owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))
        await svc.set_grant(owner, board.id, "backend-ana", "contributor")
        assert audit.has("kanban_grant_set")
        assert [g.role for g in await svc.list_grants(owner, board.id)] == ["contributor"]
        await svc.remove_grant(owner, board.id, "backend-ana")
        assert audit.has("kanban_grant_removed")
        assert await svc.list_grants(owner, board.id) == []

    async def test_set_grant_rejects_unknown_agent(self):
        svc, _boards, _audit, _users, owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))
        with pytest.raises(NotFoundError):
            await svc.set_grant(owner, board.id, "ghost-agent", "viewer")

    async def test_grant_management_is_owner_only(self):
        svc, _boards, _audit, users, owner = await _setup()
        member = await users.add(User(email="m@amp.local", name="M", password_hash="x"))
        board = await svc.create_board(owner, BoardCreate(name="B", visibility="team"))
        # a team member can see the board but cannot manage its grants
        with pytest.raises(PermissionDeniedError):
            await svc.set_grant(member, board.id, "backend-ana", "viewer")
        with pytest.raises(PermissionDeniedError):
            await svc.list_grants(member, board.id)
