"""Kanban board service (Epic 06). Owns authorization and the ordering algebra;
routes and the WS handler only ever call this layer (docs/ARCHITECTURE.md).

Authorization (6.1, humans): the board owner has full control; on a `team`
board every member is editor-equivalent (manage columns + cards); a `private`
board is owner-only for humans. Board governance (settings, delete, grants) is
owner/admin only. Per-agent grants restrict AGENTS and are layered on in 6.3.

Security: `created_by`/`author`/`assignee` are stamped from the AUTHENTICATED
actor, never trusted from the client (anti-spoof). Every mutation is audited.
"""

from app.models.kanban import KanbanBoard, KanbanCard, KanbanCardComment, KanbanColumn
from app.models.user import User, utcnow
from app.repositories.audit_repo import AuditRepository
from app.repositories.kanban_repo import KanbanRepository
from app.schemas.kanban import (
    BoardCreate,
    BoardUpdate,
    CardCreate,
    CardUpdate,
    ColumnCreate,
    ColumnUpdate,
    CommentCreate,
)
from app.services.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.services.kanban_rank import rank_between

# Default columns a new board is seeded with; the landing column (new + event
# cards land here) is "A fazer". User-facing copy stays pt-BR.
DEFAULT_COLUMNS: list[tuple[str, bool]] = [
    ("Backlog", False),
    ("A fazer", True),
    ("Fazendo", False),
    ("Revisão", False),
    ("Concluído", False),
]


class KanbanService:
    def __init__(self, boards: KanbanRepository, audit: AuditRepository) -> None:
        self._boards = boards
        self._audit = audit

    # ---- boards ----

    async def create_board(self, user: User, data: BoardCreate) -> KanbanBoard:
        board = await self._boards.add_board(
            KanbanBoard(
                owner_id=user.id,
                name=data.name.strip(),
                visibility=data.visibility,
                default_agent_role=data.default_agent_role,
            )
        )
        # Seed the default columns in one transaction, ranked left→right.
        columns: list[KanbanColumn] = []
        prev: str | None = None
        for name, is_landing in DEFAULT_COLUMNS:
            prev = rank_between(prev, None)
            columns.append(
                KanbanColumn(board_id=board.id, name=name, rank=prev, is_landing=is_landing)
            )
        await self._boards.add_columns(columns)
        await self._audit.record(
            "kanban_board_created",
            actor=user.email,
            detail={"board_id": board.id, "name": board.name, "visibility": board.visibility},
        )
        return board

    async def list_boards(self, user: User) -> list[KanbanBoard]:
        return await self._boards.list_visible_boards(user.id, is_admin=user.role == "admin")

    async def get_board(self, user: User, board_id: int) -> KanbanBoard:
        return await self._visible_board(user, board_id)

    async def get_board_full(
        self, user: User, board_id: int
    ) -> tuple[KanbanBoard, list[KanbanColumn], list[KanbanCard]]:
        board = await self._visible_board(user, board_id)
        columns = await self._boards.list_columns(board_id)
        cards = await self._boards.list_cards(board_id)
        return board, columns, cards

    async def update_board(self, user: User, board_id: int, data: BoardUpdate) -> KanbanBoard:
        board = await self._owned_board(user, board_id)
        changed: dict = {}
        if data.name is not None:
            board.name = data.name.strip()
            changed["name"] = board.name
        if data.visibility is not None:
            board.visibility = data.visibility
            changed["visibility"] = board.visibility
        if data.default_agent_role is not None:
            board.default_agent_role = data.default_agent_role
            changed["default_agent_role"] = board.default_agent_role
        await self._boards.save_board(board)
        await self._audit.record(
            "kanban_board_updated", actor=user.email, detail={"board_id": board_id, **changed}
        )
        return board

    async def delete_board(self, user: User, board_id: int) -> None:
        board = await self._owned_board(user, board_id)
        await self._boards.delete_board(board)
        await self._audit.record(
            "kanban_board_deleted", actor=user.email, detail={"board_id": board_id}
        )

    # ---- columns ----

    async def create_column(self, user: User, board_id: int, data: ColumnCreate) -> KanbanColumn:
        await self._visible_board(user, board_id)
        existing = await self._boards.list_columns(board_id)
        rank = rank_between(existing[-1].rank if existing else None, None)
        column = await self._boards.add_column(
            KanbanColumn(
                board_id=board_id,
                name=data.name.strip(),
                rank=rank,
                wip_limit=data.wip_limit,
                is_landing=False,
            )
        )
        await self._audit.record(
            "kanban_column_created",
            actor=user.email,
            detail={"board_id": board_id, "column_id": column.id, "name": column.name},
        )
        return column

    async def update_column(
        self, user: User, board_id: int, column_id: int, data: ColumnUpdate
    ) -> KanbanColumn:
        await self._visible_board(user, board_id)
        column = await self._column_of_board(board_id, column_id)
        if data.name is not None:
            column.name = data.name.strip()
        if data.wip_limit is not None:
            # 0 clears the limit (unlimited); a positive value sets it.
            column.wip_limit = None if data.wip_limit == 0 else data.wip_limit
        if data.is_landing:
            # Exactly one landing column per board.
            await self._boards.clear_landing(board_id)
            column.is_landing = True
        await self._boards.save_column(column)
        await self._audit.record(
            "kanban_column_updated",
            actor=user.email,
            detail={"board_id": board_id, "column_id": column_id},
        )
        return column

    async def delete_column(self, user: User, board_id: int, column_id: int) -> None:
        await self._visible_board(user, board_id)
        column = await self._column_of_board(board_id, column_id)
        if await self._boards.count_cards_in_column(column_id) > 0:
            raise ConflictError("Mova ou exclua os cards antes de remover a coluna.")
        if column.is_landing:
            raise ConflictError("Defina outra coluna como destino antes de remover esta.")
        await self._boards.delete_column(column)
        await self._audit.record(
            "kanban_column_deleted",
            actor=user.email,
            detail={"board_id": board_id, "column_id": column_id},
        )

    # ---- cards ----

    async def create_card(self, user: User, board_id: int, data: CardCreate) -> KanbanCard:
        await self._visible_board(user, board_id)
        column = await self._resolve_landing(board_id, data.column_id)
        rank = rank_between(await self._boards.last_rank_in_column(column.id), None)
        card = await self._boards.add_card(
            KanbanCard(
                board_id=board_id,
                column_id=column.id,
                rank=rank,
                title=data.title.strip(),
                body=data.body,
                created_by=f"user:{user.id}",  # authenticated actor (anti-spoof)
                assignee=data.assignee,
                priority=data.priority,
            )
        )
        await self._audit.record(
            "kanban_card_created",
            actor=user.email,
            detail={"board_id": board_id, "card_id": card.id, "column_id": column.id},
        )
        return card

    async def get_card(self, user: User, card_id: int) -> KanbanCard:
        card = await self._boards.get_card(card_id)
        if card is None:
            raise NotFoundError("Card não encontrado.")
        await self._visible_board(user, card.board_id)
        return card

    async def update_card(self, user: User, card_id: int, data: CardUpdate) -> KanbanCard:
        card = await self.get_card(user, card_id)
        if data.expected_version is not None and card.version != data.expected_version:
            raise ConflictError("O card foi alterado por outra pessoa; recarregue e tente de novo.")
        if data.title is not None:
            card.title = data.title.strip()
        if data.body is not None:
            card.body = data.body
        if data.clear_assignee:
            card.assignee = None
        elif data.assignee is not None:
            card.assignee = data.assignee
        if data.priority is not None:
            card.priority = data.priority
        card.version += 1
        card.updated_at = utcnow()
        await self._boards.save_card(card)
        await self._audit.record(
            "kanban_card_updated",
            actor=user.email,
            detail={"board_id": card.board_id, "card_id": card_id, "version": card.version},
        )
        return card

    async def delete_card(self, user: User, card_id: int) -> None:
        card = await self.get_card(user, card_id)
        await self._boards.delete_card(card)
        await self._audit.record(
            "kanban_card_deleted",
            actor=user.email,
            detail={"board_id": card.board_id, "card_id": card_id},
        )

    # ---- comments ----

    async def list_comments(self, user: User, card_id: int) -> list[KanbanCardComment]:
        card = await self.get_card(user, card_id)
        return await self._boards.list_comments(card.id)

    async def add_comment(self, user: User, card_id: int, data: CommentCreate) -> KanbanCardComment:
        card = await self.get_card(user, card_id)
        comment = await self._boards.add_comment(
            KanbanCardComment(
                card_id=card.id,
                author=f"user:{user.id}",  # authenticated actor (anti-spoof)
                body=data.body,
            )
        )
        await self._audit.record(
            "kanban_comment_added",
            actor=user.email,
            detail={"board_id": card.board_id, "card_id": card_id, "comment_id": comment.id},
        )
        return comment

    # ---- internals ----

    def _human_can_see(self, user: User, board: KanbanBoard) -> bool:
        return user.role == "admin" or board.owner_id == user.id or board.visibility == "team"

    async def _visible_board(self, user: User, board_id: int) -> KanbanBoard:
        """The board if the human may access it, else 404 (never leak existence)."""
        board = await self._boards.get_board(board_id)
        if board is None or not self._human_can_see(user, board):
            raise NotFoundError("Quadro não encontrado.")
        return board

    async def _owned_board(self, user: User, board_id: int) -> KanbanBoard:
        """Board governance (settings/delete/grants): owner or admin only."""
        board = await self._visible_board(user, board_id)
        if board.owner_id != user.id and user.role != "admin":
            raise PermissionDeniedError("Apenas o dono do quadro (ou admin) pode fazer isso.")
        return board

    async def _column_of_board(self, board_id: int, column_id: int) -> KanbanColumn:
        column = await self._boards.get_column(column_id)
        if column is None or column.board_id != board_id:
            raise NotFoundError("Coluna não encontrada.")
        return column

    async def _resolve_landing(self, board_id: int, column_id: int | None) -> KanbanColumn:
        if column_id is not None:
            return await self._column_of_board(board_id, column_id)
        landing = await self._boards.landing_column(board_id)
        if landing is None:
            # Defensive: a board always has a landing column, but fall back to the
            # first column rather than fail a create.
            columns = await self._boards.list_columns(board_id)
            if not columns:
                raise ConflictError("O quadro não tem colunas.")
            return columns[0]
        return landing
