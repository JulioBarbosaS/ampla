"""Kanban REST API (Epic 06). Humans manage the board here; agents act over the
WS (§6.4). Routes are thin: they authenticate the user and delegate to
KanbanService, which owns all authorization (docs/ARCHITECTURE.md layer rules).
Move (§6.2) and grants (§6.3) are added in their own slices."""

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_current_agent,
    get_current_user,
    get_kanban_service,
    get_message_service,
)
from app.models.agent import Agent
from app.models.user import User
from app.schemas.kanban import (
    BoardCreate,
    BoardFull,
    BoardOut,
    BoardUpdate,
    CardCreate,
    CardMove,
    CardOriginOut,
    CardOut,
    CardUpdate,
    ColumnCreate,
    ColumnOut,
    ColumnUpdate,
    CommentCreate,
    CommentOut,
    DepCreate,
    GrantOut,
    GrantSet,
    MemberAdd,
    MemberOut,
)
from app.services.kanban_service import KanbanService
from app.services.message_service import MessageService

router = APIRouter(prefix="/api/kanban", tags=["kanban"])


# ---- boards ----


@router.post("/boards", response_model=BoardOut, status_code=201)
async def create_board(
    body: BoardCreate,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> BoardOut:
    return BoardOut.model_validate(await svc.create_board(user, body))


@router.get("/boards", response_model=list[BoardOut])
async def list_boards(
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> list[BoardOut]:
    return [BoardOut.model_validate(b) for b in await svc.list_boards(user)]


@router.get("/boards/{board_id}", response_model=BoardOut)
async def get_board(
    board_id: int,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> BoardOut:
    return BoardOut.model_validate(await svc.get_board(user, board_id))


@router.get("/boards/{board_id}/full", response_model=BoardFull)
async def get_board_full(
    board_id: int,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> BoardFull:
    board, columns, cards = await svc.get_board_full(user, board_id)
    return BoardFull(
        board=BoardOut.model_validate(board),
        columns=[ColumnOut.model_validate(c) for c in columns],
        cards=[CardOut.model_validate(c) for c in cards],
    )


@router.patch("/boards/{board_id}", response_model=BoardOut)
async def update_board(
    board_id: int,
    body: BoardUpdate,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> BoardOut:
    return BoardOut.model_validate(await svc.update_board(user, board_id, body))


@router.delete("/boards/{board_id}", status_code=204)
async def delete_board(
    board_id: int,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> None:
    await svc.delete_board(user, board_id)


# ---- columns ----


@router.post("/boards/{board_id}/columns", response_model=ColumnOut, status_code=201)
async def create_column(
    board_id: int,
    body: ColumnCreate,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> ColumnOut:
    return ColumnOut.model_validate(await svc.create_column(user, board_id, body))


@router.patch("/boards/{board_id}/columns/{column_id}", response_model=ColumnOut)
async def update_column(
    board_id: int,
    column_id: int,
    body: ColumnUpdate,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> ColumnOut:
    return ColumnOut.model_validate(await svc.update_column(user, board_id, column_id, body))


@router.delete("/boards/{board_id}/columns/{column_id}", status_code=204)
async def delete_column(
    board_id: int,
    column_id: int,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> None:
    await svc.delete_column(user, board_id, column_id)


# ---- cards ----


@router.post("/boards/{board_id}/cards", response_model=CardOut, status_code=201)
async def create_card(
    board_id: int,
    body: CardCreate,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> CardOut:
    return CardOut.model_validate(await svc.create_card(user, board_id, body))


@router.get("/cards/{card_id}", response_model=CardOut)
async def get_card(
    card_id: int,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> CardOut:
    return CardOut.model_validate(await svc.get_card(user, card_id))


@router.get("/cards/{card_id}/origin", response_model=CardOriginOut)
async def get_card_origin(
    card_id: int,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
    messages: MessageService = Depends(get_message_service),
) -> CardOriginOut:
    """Resolve the card's `origin` into a deep-link to its source conversation
    (Epic 07). KanbanService authorizes the card (board visibility); MessageService
    authorizes + resolves the conversation, so a private conversation never leaks."""
    card = await svc.get_card(user, card_id)  # 404 + board visibility
    return CardOriginOut.model_validate(await messages.resolve_origin(user, card.origin))


@router.patch("/cards/{card_id}", response_model=CardOut)
async def update_card(
    card_id: int,
    body: CardUpdate,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> CardOut:
    return CardOut.model_validate(await svc.update_card(user, card_id, body))


@router.delete("/cards/{card_id}", status_code=204)
async def delete_card(
    card_id: int,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> None:
    await svc.delete_card(user, card_id)


@router.post("/cards/{card_id}/move", response_model=CardOut)
async def move_card(
    card_id: int,
    body: CardMove,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> CardOut:
    card = await svc.move_card(
        user,
        card_id,
        body.to_column_id,
        before_id=body.before_id,
        after_id=body.after_id,
        expected_version=body.expected_version,
    )
    return CardOut.model_validate(card)


# ---- comments ----


@router.get("/cards/{card_id}/comments", response_model=list[CommentOut])
async def list_comments(
    card_id: int,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> list[CommentOut]:
    return [CommentOut.model_validate(c) for c in await svc.list_comments(user, card_id)]


@router.post("/cards/{card_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    card_id: int,
    body: CommentCreate,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> CommentOut:
    return CommentOut.model_validate(await svc.add_comment(user, card_id, body))


# ---- dependencies (DAG — Epic 06 · 6.7) ----


@router.get("/cards/{card_id}/dependencies", response_model=list[CardOut])
async def list_dependencies(
    card_id: int,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> list[CardOut]:
    return [CardOut.model_validate(c) for c in await svc.list_dependencies(user, card_id)]


@router.post("/cards/{card_id}/dependencies", response_model=list[CardOut], status_code=201)
async def add_dependency(
    card_id: int,
    body: DepCreate,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> list[CardOut]:
    await svc.add_dependency(user, card_id, body.depends_on_id)
    return [CardOut.model_validate(c) for c in await svc.list_dependencies(user, card_id)]


@router.delete("/cards/{card_id}/dependencies/{depends_on_id}", status_code=204)
async def remove_dependency(
    card_id: int,
    depends_on_id: int,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> None:
    await svc.remove_dependency(user, card_id, depends_on_id)


# ---- agent reads (authenticated by agent key — Epic 06 · 6.4) ----
#
# Writes go over the WS (kanban_action); reads need real data, so the daemon
# proxies these GETs with its agent key. Same per-agent capability as the WS
# path — a dev-only board never appears here.


@router.get("/agent/boards", response_model=list[BoardOut])
async def agent_list_boards(
    agent: Agent = Depends(get_current_agent),
    svc: KanbanService = Depends(get_kanban_service),
) -> list[BoardOut]:
    return [BoardOut.model_validate(b) for b in await svc.agent_list_boards(agent.slug)]


@router.get("/agent/boards/{board_id}/full", response_model=BoardFull)
async def agent_board_full(
    board_id: int,
    mine: bool = False,
    agent: Agent = Depends(get_current_agent),
    svc: KanbanService = Depends(get_kanban_service),
) -> BoardFull:
    board, columns, cards = await svc.agent_get_board_full(agent.slug, board_id, mine=mine)
    return BoardFull(
        board=BoardOut.model_validate(board),
        columns=[ColumnOut.model_validate(c) for c in columns],
        cards=[CardOut.model_validate(c) for c in cards],
    )


# ---- per-agent grants (owner/admin only — Epic 06 · 6.3) ----


@router.get("/boards/{board_id}/grants", response_model=list[GrantOut])
async def list_grants(
    board_id: int,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> list[GrantOut]:
    return [GrantOut.model_validate(g) for g in await svc.list_grants(user, board_id)]


@router.put("/boards/{board_id}/grants", response_model=GrantOut)
async def set_grant(
    board_id: int,
    body: GrantSet,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> GrantOut:
    grant = await svc.set_grant(user, board_id, body.agent_slug, body.role)
    return GrantOut.model_validate(grant)


@router.delete("/boards/{board_id}/grants/{agent_slug}", status_code=204)
async def remove_grant(
    board_id: int,
    agent_slug: str,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> None:
    await svc.remove_grant(user, board_id, agent_slug)


# ---- board members (per-user sharing — Epic 10) ----
#
# Sharing a board with specific people. Management is owner/admin only; once
# shared, a member sees + edits the board like a team member and may grant their
# OWN agents a role on it (the grant routes above enforce that authority).


def _member_out(member, target) -> MemberOut:
    return MemberOut(
        board_id=member.board_id,
        user_id=member.user_id,
        name=target.name,
        email=target.email,
        created_at=member.created_at,
    )


@router.get("/boards/{board_id}/members", response_model=list[MemberOut])
async def list_members(
    board_id: int,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> list[MemberOut]:
    return [_member_out(m, u) for m, u in await svc.list_members(user, board_id)]


@router.post("/boards/{board_id}/members", response_model=MemberOut, status_code=201)
async def add_member(
    board_id: int,
    body: MemberAdd,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> MemberOut:
    member, target = await svc.add_member(user, board_id, body.user_id)
    return _member_out(member, target)


@router.delete("/boards/{board_id}/members/{user_id}", status_code=204)
async def remove_member(
    board_id: int,
    user_id: int,
    user: User = Depends(get_current_user),
    svc: KanbanService = Depends(get_kanban_service),
) -> None:
    await svc.remove_member(user, board_id, user_id)
