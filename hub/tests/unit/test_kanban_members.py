"""Per-user board sharing (Epic 10): a private board can be shared with specific
people; a member sees/edits it and may grant their OWN agents — never someone
else's. Member management stays owner/admin governance."""

import pytest

from app.models.agent import Agent
from app.models.user import User
from app.schemas.kanban import BoardCreate, CardCreate
from app.services.errors import NotFoundError, PermissionDeniedError
from app.services.kanban_service import KanbanService
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
    joao = await users.add(User(email="joao@amp.local", name="João", password_hash="x"))
    maria = await users.add(User(email="maria@amp.local", name="Maria", password_hash="x"))
    await agents.add(Agent(slug="joao-backend", user_id=joao.id, display_name="João Backend"))
    await agents.add(Agent(slug="maria-front", user_id=maria.id, display_name="Maria Front"))
    svc = KanbanService(boards=boards, audit=audit, agents=agents, users=users)
    return svc, audit, owner, joao, maria


class TestVisibility:
    async def test_member_sees_private_board_non_member_does_not(self):
        svc, _audit, owner, joao, maria = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="Secreto", visibility="private"))
        # before sharing: neither João nor Maria can see it
        with pytest.raises(NotFoundError):
            await svc.get_board(joao, board.id)
        await svc.add_member(owner, board.id, joao.id)
        # João now sees it; Maria (not shared) still 404s — never leak existence
        assert (await svc.get_board(joao, board.id)).id == board.id
        with pytest.raises(NotFoundError):
            await svc.get_board(maria, board.id)

    async def test_shared_board_appears_in_member_board_list(self):
        svc, _audit, owner, joao, _maria = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="Secreto", visibility="private"))
        assert [b.id for b in await svc.list_boards(joao)] == []
        await svc.add_member(owner, board.id, joao.id)
        assert board.id in [b.id for b in await svc.list_boards(joao)]

    async def test_member_can_edit_like_a_team_member(self):
        svc, _audit, owner, joao, _maria = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="Secreto", visibility="private"))
        await svc.add_member(owner, board.id, joao.id)
        # human members are never capability-gated — João can create a card
        card = await svc.create_card(joao, board.id, CardCreate(title="Pelo membro"))
        assert card.created_by == f"user:{joao.id}"


class TestMemberManagement:
    async def test_add_and_remove_are_owner_only_and_audited(self):
        svc, audit, owner, joao, maria = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B", visibility="private"))
        member, target = await svc.add_member(owner, board.id, joao.id)
        assert member.user_id == joao.id and target.email == "joao@amp.local"
        assert audit.has("kanban_member_added")
        # a non-owner (even a member) cannot manage the sharing list
        await svc.add_member(owner, board.id, maria.id)
        with pytest.raises(PermissionDeniedError):
            await svc.add_member(joao, board.id, maria.id)
        with pytest.raises(PermissionDeniedError):
            await svc.remove_member(joao, board.id, maria.id)
        with pytest.raises(PermissionDeniedError):
            await svc.list_members(joao, board.id)
        await svc.remove_member(owner, board.id, joao.id)
        assert audit.has("kanban_member_removed")

    async def test_add_member_is_idempotent(self):
        svc, _audit, owner, joao, _maria = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B", visibility="private"))
        await svc.add_member(owner, board.id, joao.id)
        await svc.add_member(owner, board.id, joao.id)  # no duplicate
        members = await svc.list_members(owner, board.id)
        assert [m.user_id for m, _ in members] == [joao.id]

    async def test_add_member_rejects_unknown_user(self):
        svc, _audit, owner, _joao, _maria = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B", visibility="private"))
        with pytest.raises(NotFoundError):
            await svc.add_member(owner, board.id, 9999)

    async def test_remove_member_is_idempotent(self):
        svc, _audit, owner, joao, _maria = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B", visibility="private"))
        await svc.remove_member(owner, board.id, joao.id)  # never a member → no-op
        assert await svc.list_members(owner, board.id) == []


class TestMemberGrantAuthority:
    async def test_member_grants_only_their_own_agent(self):
        svc, audit, owner, joao, maria = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B", visibility="private"))
        await svc.add_member(owner, board.id, joao.id)
        # João grants HIS agent → ok
        await svc.set_grant(joao, board.id, "joao-backend", "contributor")
        assert audit.has("kanban_grant_set")
        assert await svc.agent_role(board, "joao-backend") == "contributor"
        # João cannot grant Maria's agent
        with pytest.raises(PermissionDeniedError):
            await svc.set_grant(joao, board.id, "maria-front", "viewer")

    async def test_member_revokes_only_their_own_agent(self):
        svc, _audit, owner, joao, _maria = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B", visibility="private"))
        await svc.add_member(owner, board.id, joao.id)
        # owner grants Maria's agent; João (a member) must not be able to revoke it
        await svc.set_grant(owner, board.id, "maria-front", "viewer")
        with pytest.raises(PermissionDeniedError):
            await svc.remove_grant(joao, board.id, "maria-front")
        # but João can revoke his own
        await svc.set_grant(joao, board.id, "joao-backend", "viewer")
        await svc.remove_grant(joao, board.id, "joao-backend")
        assert await svc.agent_role(board, "joao-backend") == "none"

    async def test_owner_grants_any_agent(self):
        svc, _audit, owner, _joao, _maria = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B", visibility="private"))
        # owner may grant an agent owned by anyone
        await svc.set_grant(owner, board.id, "maria-front", "editor")
        assert await svc.agent_role(board, "maria-front") == "editor"

    async def test_non_member_cannot_grant_even_own_agent(self):
        svc, _audit, owner, _joao, maria = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B", visibility="private"))
        # Maria isn't shared onto the board → 404 (existence not leaked), not 403
        with pytest.raises(NotFoundError):
            await svc.set_grant(maria, board.id, "maria-front", "viewer")

    async def test_member_can_read_grants(self):
        svc, _audit, owner, joao, _maria = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B", visibility="private"))
        await svc.add_member(owner, board.id, joao.id)
        await svc.set_grant(owner, board.id, "maria-front", "viewer")
        # a member may read the whole grant list (to manage their own access)
        assert [g.agent_slug for g in await svc.list_grants(joao, board.id)] == ["maria-front"]

    async def test_grant_authority_does_not_leak_across_boards(self):
        svc, _audit, owner, joao, _maria = await _setup()
        shared = await svc.create_board(owner, BoardCreate(name="Shared", visibility="private"))
        other = await svc.create_board(owner, BoardCreate(name="Other", visibility="private"))
        await svc.add_member(owner, shared.id, joao.id)
        # João is a member of `shared` only → cannot grant on `other`
        with pytest.raises(NotFoundError):
            await svc.set_grant(joao, other.id, "joao-backend", "viewer")
