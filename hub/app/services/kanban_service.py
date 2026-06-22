"""Kanban board service (Epic 06). Owns authorization and the ordering algebra;
routes and the WS handler only ever call this layer (docs/ARCHITECTURE.md).

Authorization (6.1, humans): the board owner has full control; on a `team`
board every member is editor-equivalent (manage columns + cards); a `private`
board is owner-only for humans. Board governance (settings, delete, grants) is
owner/admin only. Per-agent grants restrict AGENTS and are layered on in 6.3.

Security: `created_by`/`author`/`assignee` are stamped from the AUTHENTICATED
actor, never trusted from the client (anti-spoof). Every mutation is audited.
"""

from app.models.kanban import (
    KanbanAgentGrant,
    KanbanBoard,
    KanbanCard,
    KanbanCardComment,
    KanbanColumn,
)
from app.models.user import User, utcnow
from app.repositories.agent_repo import AgentRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.kanban_repo import KanbanRepository
from app.schemas.kanban import (
    GRANTABLE_ROLES,
    BoardCreate,
    BoardUpdate,
    CardCreate,
    CardUpdate,
    ColumnCreate,
    ColumnUpdate,
    CommentCreate,
)
from app.services.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
)
from app.services.kanban_rank import RANK_LEN_MAX, rank_between, rebalance_ranks

# Bounded retries on the unique-rank backstop before falling back to a rebalance
# (Epic 06 · 6.2). A collision needs a concurrent move into the same gap, so a
# couple of retries already converges in practice.
_MOVE_RETRIES = 4


def agent_capability(role: str, action: str, *, owns_card: bool = False) -> bool:
    """Whether an AGENT with `role` may perform `action` on a board/card
    (Epic 06 · 6.3). Humans are never gated here — this restricts agents only.

    Actions: ``view`` ``comment`` ``create`` ``move`` ``edit`` ``delete``
    ``manage_columns``. ``owns_card`` is true when the agent created OR is
    assigned the target card (a contributor may only touch its own/assigned).
    """
    if role == "viewer":
        return action in {"view", "comment"}
    if role == "contributor":
        if action in {"view", "comment", "create"}:
            return True
        if action in {"move", "edit"}:
            return owns_card
        return False
    if role == "editor":
        return action in {"view", "comment", "create", "move", "edit", "delete", "manage_columns"}
    return False  # `none` (dev-only board) or an unknown role → no access


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
    def __init__(
        self,
        boards: KanbanRepository,
        audit: AuditRepository,
        agents: AgentRepository | None = None,
    ) -> None:
        self._boards = boards
        self._audit = audit
        # Used to validate grant targets and (in 6.4) to attribute agent actions.
        self._agents = agents

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

    # ---- move (ordering & concurrency core — Epic 06 · 6.2) ----

    async def move_card(
        self,
        user: User,
        card_id: int,
        to_column_id: int,
        *,
        before_id: int | None,
        after_id: int | None,
        expected_version: int,
    ) -> KanbanCard:
        """Reorder/relocate a card between the neighbours the client saw
        (`before_id`/`after_id`), guarded by its `expected_version`.

        Defense in depth (§6.2): (1) the move runs as one serialized write txn —
        SQLite admits one writer at a time, the pessimistic lock for free;
        (2) the rank is recomputed from the *current* neighbours, so a stale
        client view can't silently misorder; (3) the optimistic `version` rejects
        a lost update with 409; (4) WIP is enforced inside the write txn (no
        TOCTOU); (5) the unique `(column_id, rank)` index backstops a midpoint
        collision → bounded retry → rebalance.
        """
        card = await self.get_card(user, card_id)  # 404 + visibility
        if card.version != expected_version:
            raise ConflictError("O card foi alterado por outra pessoa; recarregue e tente de novo.")
        dest = await self._column_of_board(card.board_id, to_column_id)

        lo, hi = await self._move_bounds(dest.id, card, before_id, after_id)
        new_rank = rank_between(lo, hi)
        if len(new_rank) > RANK_LEN_MAX:
            # Gap exhausted in this column — re-spread it, then recompute.
            await self._rebalance(dest.id)
            card = await self._boards.get_card(card_id) or card
            lo, hi = await self._move_bounds(dest.id, card, before_id, after_id)
            new_rank = rank_between(lo, hi)

        for _ in range(_MOVE_RETRIES):
            result = await self._boards.commit_move(card, dest.id, new_rank, dest.wip_limit)
            if result == "ok":
                return await self._record_move(user, card, dest)
            if result == "wip_full":
                raise ConflictError(f"A coluna {dest.name!r} atingiu o limite de cards.")
            # collision: another move grabbed this exact rank — squeeze strictly
            # below it (toward `lo`), which targets an empty slot.
            hi = new_rank
            new_rank = rank_between(lo, hi)

        # Pathological run of collisions: rebalance and place once more.
        await self._rebalance(dest.id)
        card = await self._boards.get_card(card_id) or card
        lo, hi = await self._move_bounds(dest.id, card, before_id, after_id)
        result = await self._boards.commit_move(card, dest.id, rank_between(lo, hi), dest.wip_limit)
        if result != "ok":
            raise ConflictError("Não foi possível posicionar o card; recarregue e tente de novo.")
        return await self._record_move(user, card, dest)

    async def _record_move(self, user: User, card: KanbanCard, dest: KanbanColumn) -> KanbanCard:
        await self._audit.record(
            "kanban_card_moved",
            actor=user.email,
            detail={
                "board_id": card.board_id,
                "card_id": card.id,
                "to_column_id": dest.id,
                "version": card.version,
            },
        )
        return card

    async def _move_bounds(
        self, dest_id: int, card: KanbanCard, before_id: int | None, after_id: int | None
    ) -> tuple[str | None, str | None]:
        """Lower/upper rank bounds for the destination, from the anchors the
        client saw, re-read now (intent, not an absolute index)."""
        before_rank = await self._anchor_rank(dest_id, before_id, card) if before_id else None
        after_rank = await self._anchor_rank(dest_id, after_id, card) if after_id else None
        if before_rank is None and after_rank is None:
            # No anchors → append to the end of the destination (excluding self).
            ranks = [
                c.rank for c in await self._boards.list_cards_in_column(dest_id) if c.id != card.id
            ]
            before_rank = ranks[-1] if ranks else None
        if before_rank is not None and after_rank is not None and before_rank >= after_rank:
            raise ConflictError("A posição informada está desatualizada; recarregue o quadro.")
        return before_rank, after_rank

    async def _anchor_rank(self, dest_id: int, anchor_id: int, card: KanbanCard) -> str:
        if anchor_id == card.id:
            raise InvalidInputError("Um card não pode ser âncora de si mesmo.")
        anchor = await self._boards.get_card(anchor_id)
        if anchor is None or anchor.column_id != dest_id:
            # The client's neighbour view is stale → refetch and retry.
            raise ConflictError("A posição informada está desatualizada; recarregue o quadro.")
        return anchor.rank

    async def _rebalance(self, column_id: int) -> None:
        count = await self._boards.count_cards_in_column(column_id)
        await self._boards.rebalance_column(column_id, rebalance_ranks(count))

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

    # ---- grants & capability (per-agent, per-board — Epic 06 · 6.3) ----

    async def list_grants(self, user: User, board_id: int) -> list[KanbanAgentGrant]:
        await self._owned_board(user, board_id)  # governance: owner/admin only
        return await self._boards.list_grants(board_id)

    async def set_grant(
        self, user: User, board_id: int, agent_slug: str, role: str
    ) -> KanbanAgentGrant:
        """Grant an agent a role on a board (owner/admin). A privileged action —
        granting write to an AI is treated like relaxing a guardrail: audited as
        `kanban_grant_set` (and behind the danger-zone confirm in the UI, §6.6)."""
        await self._owned_board(user, board_id)
        if role not in GRANTABLE_ROLES:
            raise InvalidInputError(f"Papel inválido: {role!r}.")
        if self._agents is not None and await self._agents.get(agent_slug) is None:
            raise NotFoundError(f"Agente {agent_slug!r} não existe.")
        grant = await self._boards.get_grant(board_id, agent_slug)
        if grant is None:
            grant = await self._boards.add_grant(
                KanbanAgentGrant(board_id=board_id, agent_slug=agent_slug, role=role)
            )
        else:
            grant.role = role
            await self._boards.save_grant(grant)
        await self._audit.record(
            "kanban_grant_set",
            actor=user.email,
            detail={"board_id": board_id, "agent": agent_slug, "role": role},
        )
        return grant

    async def remove_grant(self, user: User, board_id: int, agent_slug: str) -> None:
        await self._owned_board(user, board_id)
        grant = await self._boards.get_grant(board_id, agent_slug)
        if grant is None:
            return  # idempotent
        await self._boards.delete_grant(grant)
        await self._audit.record(
            "kanban_grant_removed",
            actor=user.email,
            detail={"board_id": board_id, "agent": agent_slug},
        )

    async def agent_role(self, board: KanbanBoard, agent_slug: str) -> str:
        """The agent's effective role on a board: an explicit grant, else the
        board's `default_agent_role` (`none` = dev-only)."""
        grant = await self._boards.get_grant(board.id, agent_slug)
        return grant.role if grant else board.default_agent_role

    @staticmethod
    def _agent_owns(card: KanbanCard, agent_slug: str) -> bool:
        """A contributor's reach: cards it created OR is assigned."""
        return card.created_by == agent_slug or card.assignee == agent_slug

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
