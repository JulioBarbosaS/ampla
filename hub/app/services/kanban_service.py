"""Kanban board service (Epic 06). Owns authorization and the ordering algebra;
routes and the WS handler only ever call this layer (docs/ARCHITECTURE.md).

Authorization (6.1, humans): the board owner has full control; on a `team`
board every member is editor-equivalent (manage columns + cards); a `private`
board is owner-only for humans, plus anyone it was explicitly shared with
(Epic 10 membership). Board governance (settings, delete, members) is owner/admin
only. Per-agent grants restrict AGENTS (§6.3); the owner/admin may grant any
agent, and a board-visible user may grant only their OWN agents (Epic 10).

Security: `created_by`/`author`/`assignee` are stamped from the AUTHENTICATED
actor, never trusted from the client (anti-spoof). Every mutation is audited.
"""

from app.core.mentions import parse_mentions
from app.models.kanban import (
    KanbanAgentGrant,
    KanbanBoard,
    KanbanBoardMember,
    KanbanCard,
    KanbanCardComment,
    KanbanCardDep,
    KanbanColumn,
)
from app.models.user import User, utcnow
from app.repositories.agent_repo import AgentRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.kanban_repo import KanbanRepository
from app.repositories.user_repo import UserRepository
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
from app.services.notification_service import NotificationService

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


# Default columns a new board is seeded with (name, is_landing, is_done). The
# landing column (new + event cards land here) is "A fazer"; "Concluído" is the
# terminal column for dependency gating (§6.7). User-facing copy stays pt-BR.
DEFAULT_COLUMNS: list[tuple[str, bool, bool]] = [
    ("Backlog", False, False),
    ("A fazer", True, False),
    ("Fazendo", False, False),
    ("Revisão", False, False),
    ("Concluído", False, True),
]


class KanbanService:
    def __init__(
        self,
        boards: KanbanRepository,
        audit: AuditRepository,
        agents: AgentRepository | None = None,
        notifications: NotificationService | None = None,
        users: UserRepository | None = None,
    ) -> None:
        self._boards = boards
        self._audit = audit
        # Used to validate grant targets and (in 6.4) to attribute agent actions.
        self._agents = agents
        # Drives the Inbox integration (Epic 06 · 6.5): assignment / move / comment
        # notifications. Optional so read-only builds stay lightweight.
        self._notifications = notifications
        # Validates board-member targets (Epic 10 · per-user board sharing).
        self._users = users

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
        for name, is_landing, is_done in DEFAULT_COLUMNS:
            prev = rank_between(prev, None)
            columns.append(
                KanbanColumn(
                    board_id=board.id,
                    name=name,
                    rank=prev,
                    is_landing=is_landing,
                    is_done=is_done,
                )
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
        await self._attach_deps(board_id, cards)
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
        if data.auto_card_on_delegation is not None:
            board.auto_card_on_delegation = data.auto_card_on_delegation
            changed["auto_card_on_delegation"] = board.auto_card_on_delegation
        if data.auto_card_on_escalation is not None:
            board.auto_card_on_escalation = data.auto_card_on_escalation
            changed["auto_card_on_escalation"] = board.auto_card_on_escalation
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
        if data.is_done is not None:
            column.is_done = data.is_done  # terminal column for dependency gating
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

    # Origin kinds a human may stamp when turning a conversation into a card
    # (Epic 07). delegation/escalation are system-only, never client-settable.
    _CLIENT_ORIGIN_KINDS = ("message", "thread")

    async def create_card(self, user: User, board_id: int, data: CardCreate) -> KanbanCard:
        await self._visible_board(user, board_id)
        return await self._insert_card(
            board_id,
            data,
            created_by=f"user:{user.id}",
            audit_actor=user.email,
            origin=self._validate_client_origin(data.origin),
        )

    def _validate_client_origin(self, origin: dict | None) -> dict | None:
        """A human-supplied origin (conversation → card) may only reference a
        message/thread; the resolver re-authorizes it on read (Epic 07)."""
        if origin is None:
            return None
        if origin.get("kind") not in self._CLIENT_ORIGIN_KINDS or not isinstance(
            origin.get("id"), int
        ):
            raise InvalidInputError("Origem inválida para um card.")
        return {"kind": origin["kind"], "id": origin["id"]}

    async def _insert_card(
        self,
        board_id: int,
        data: CardCreate,
        *,
        created_by: str,
        audit_actor: str,
        origin: dict | None = None,
    ) -> KanbanCard:
        """Append a card to its column (authz already decided by the caller).
        `created_by` is the authenticated actor — `user:<id>` or an agent slug —
        never client-claimed (anti-spoof). `origin` is decided by the caller, never
        read from the client `data` (so agents can't stamp provenance)."""
        column = await self._resolve_landing(board_id, data.column_id)
        rank = rank_between(await self._boards.last_rank_in_column(column.id), None)
        card = await self._boards.add_card(
            KanbanCard(
                board_id=board_id,
                column_id=column.id,
                rank=rank,
                title=data.title.strip(),
                body=data.body,
                created_by=created_by,
                assignee=data.assignee,
                priority=data.priority,
                origin=origin,
            )
        )
        await self._audit.record(
            "kanban_card_created",
            actor=audit_actor,
            detail={"board_id": board_id, "card_id": card.id, "column_id": column.id},
        )
        if card.assignee:
            await self._notify_assignee(card, reason="task_assigned", actor=created_by)
        return card

    async def get_card(self, user: User, card_id: int) -> KanbanCard:
        card = await self._boards.get_card(card_id)
        if card is None:
            raise NotFoundError("Card não encontrado.")
        await self._visible_board(user, card.board_id)
        card.depends_on = await self._boards.dep_ids_for_card(card.id)
        return card

    async def update_card(self, user: User, card_id: int, data: CardUpdate) -> KanbanCard:
        card = await self.get_card(user, card_id)
        if data.expected_version is not None and card.version != data.expected_version:
            raise ConflictError("O card foi alterado por outra pessoa; recarregue e tente de novo.")
        if data.title is not None:
            card.title = data.title.strip()
        if data.body is not None:
            card.body = data.body
        newly_assigned = False
        if data.clear_assignee:
            card.assignee = None
        elif data.assignee is not None and data.assignee != card.assignee:
            card.assignee = data.assignee
            newly_assigned = True
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
        if newly_assigned:
            await self._notify_assignee(card, reason="task_assigned", actor=f"user:{user.id}")
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
        moved = await self._move(
            card,
            to_column_id,
            before_id=before_id,
            after_id=after_id,
            expected_version=expected_version,
            audit_actor=user.email,
        )
        await self._notify_assignee(moved, reason="state_change", actor=f"user:{user.id}")
        return moved

    async def _move(
        self,
        card: KanbanCard,
        to_column_id: int,
        *,
        before_id: int | None,
        after_id: int | None,
        expected_version: int,
        audit_actor: str,
    ) -> KanbanCard:
        """The race-safe move core (authz already decided by the caller)."""
        if card.version != expected_version:
            raise ConflictError("O card foi alterado por outra pessoa; recarregue e tente de novo.")
        dest = await self._column_of_board(card.board_id, to_column_id)
        card_id = card.id
        # Dependency gate (§6.7): can't move a blocked card into a done column.
        if dest.is_done and await self._is_blocked(card):
            raise ConflictError(
                "Card bloqueado: conclua os cards dos quais ele depende antes de finalizá-lo."
            )

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
                return await self._record_move(card, dest, audit_actor)
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
        return await self._record_move(card, dest, audit_actor)

    async def _record_move(
        self, card: KanbanCard, dest: KanbanColumn, audit_actor: str
    ) -> KanbanCard:
        card.depends_on = await self._boards.dep_ids_for_card(card.id)
        await self._audit.record(
            "kanban_card_moved",
            actor=audit_actor,
            detail={
                "board_id": card.board_id,
                "card_id": card.id,
                "to_column_id": dest.id,
                "version": card.version,
            },
        )
        # Lifecycle (Epic 07): an escalation card reaching a Done column IS the
        # resolution — the escalation has no row of its own, so the board is the
        # state. Audited whoever moved it (human, agent, or the system).
        origin = card.origin if isinstance(card.origin, dict) else {}
        if dest.is_done and origin.get("kind") == "escalation":
            await self._audit.record(
                "escalation_resolved",
                actor=audit_actor,
                detail={
                    "board_id": card.board_id,
                    "card_id": card.id,
                    "from": card.origin.get("from"),
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
        return await self._insert_comment(
            card, body=data.body, author=f"user:{user.id}", audit_actor=user.email
        )

    async def _insert_comment(
        self, card: KanbanCard, *, body: str, author: str, audit_actor: str
    ) -> KanbanCardComment:
        comment = await self._boards.add_comment(
            KanbanCardComment(card_id=card.id, author=author, body=body)
        )
        await self._audit.record(
            "kanban_comment_added",
            actor=audit_actor,
            detail={"board_id": card.board_id, "card_id": card.id, "comment_id": comment.id},
        )
        await self._notify_comment(card, body=body, actor=author)
        return comment

    # ---- agent access (via MCP/WS — Epic 06 · 6.4) ----
    #
    # Every agent action resolves the agent's per-board role (§6.3) and is denied
    # (403) when the role is insufficient — enforced HERE, at the hub, never
    # trusted from the daemon. The actor is the AUTHENTICATED socket slug.

    async def agent_list_boards(self, agent_slug: str) -> list[KanbanBoard]:
        """Boards the agent has any role on (role != none)."""
        boards = await self._boards.list_visible_boards(0, is_admin=True)
        out = []
        for board in boards:
            if await self.agent_role(board, agent_slug) != "none":
                out.append(board)
        return out

    async def agent_get_board_full(
        self, agent_slug: str, board_id: int, *, mine: bool = False
    ) -> tuple[KanbanBoard, list[KanbanColumn], list[KanbanCard]]:
        board = await self._agent_board(agent_slug, board_id)
        await self._require_agent_can(agent_slug, board, "view")
        columns = await self._boards.list_columns(board_id)
        cards = await self._boards.list_cards(board_id)
        await self._attach_deps(board_id, cards)
        if mine:  # "my tasks": created by OR assigned to this agent
            cards = [c for c in cards if self._agent_owns(c, agent_slug)]
        return board, columns, cards

    async def agent_create_card(
        self, agent_slug: str, board_id: int, data: CardCreate
    ) -> KanbanCard:
        board = await self._agent_board(agent_slug, board_id)
        await self._require_agent_can(agent_slug, board, "create")
        return await self._insert_card(
            board_id, data, created_by=agent_slug, audit_actor=agent_slug
        )

    async def agent_move_card(
        self,
        agent_slug: str,
        card_id: int,
        to_column_id: int,
        *,
        before_id: int | None,
        after_id: int | None,
        expected_version: int,
    ) -> KanbanCard:
        card = await self._existing_card(card_id)
        board = await self._agent_board(agent_slug, card.board_id)
        await self._require_agent_can(agent_slug, board, "move", card=card)
        moved = await self._move(
            card,
            to_column_id,
            before_id=before_id,
            after_id=after_id,
            expected_version=expected_version,
            audit_actor=agent_slug,
        )
        await self._notify_assignee(moved, reason="state_change", actor=agent_slug)
        return moved

    async def agent_comment(self, agent_slug: str, card_id: int, body: str) -> KanbanCardComment:
        card = await self._existing_card(card_id)
        board = await self._agent_board(agent_slug, card.board_id)
        await self._require_agent_can(agent_slug, board, "comment")
        return await self._insert_comment(
            card, body=body, author=agent_slug, audit_actor=agent_slug
        )

    async def _existing_card(self, card_id: int) -> KanbanCard:
        card = await self._boards.get_card(card_id)
        if card is None:
            raise NotFoundError("Card não encontrado.")
        return card

    async def get_board_raw(self, board_id: int) -> KanbanBoard | None:
        """The board with no authz — for the WS layer to route a `kanban_delta`
        to the right observers (owner/visibility). Never returned to a client."""
        return await self._boards.get_board(board_id)

    async def board_of_card(self, card_id: int) -> KanbanBoard | None:
        card = await self._boards.get_card(card_id)
        return await self._boards.get_board(card.board_id) if card else None

    async def board_member_ids(self, board_id: int) -> list[int]:
        """User ids explicitly shared onto a board (Epic 10) — for the WS layer to
        also route a `kanban_delta` to a private board's members. No authz; never
        returned to a client."""
        return await self._boards.member_user_ids(board_id)

    # ---- Inbox integration (Epic 06 · 6.5) ----

    async def _resolve_user_id(self, identity: str | None) -> int | None:
        """Map a card actor/assignee/mention (`user:<id>` or an agent slug) to the
        USER who should be notified — the user themselves, or the agent's owner."""
        if not identity:
            return None
        if identity.startswith("user:"):
            try:
                return int(identity[5:])
            except ValueError:
                return None
        if self._agents is not None:
            agent = await self._agents.get(identity)
            return agent.user_id if agent else None
        return None

    def _card_link(self, card: KanbanCard) -> str:
        return f"/?board={card.board_id}&card={card.id}"

    async def _notify_assignee(self, card: KanbanCard, *, reason: str, actor: str) -> None:
        """Notify the card's assignee's owner on assignment / state change. The
        actor is never notified of their own action."""
        if self._notifications is None or not card.assignee:
            return
        target = await self._resolve_user_id(card.assignee)
        actor_uid = await self._resolve_user_id(actor)
        if target is None or target == actor_uid:
            return
        title = (
            f"Você foi atribuído ao card “{card.title}”"
            if reason == "task_assigned"
            else f"O card “{card.title}” foi movido"
        )
        await self._notifications.notify(
            target,
            subject_type="kanban_card",
            subject_key=f"kanban:card:{card.id}",
            reason=reason,
            title=title,
            link=self._card_link(card),
            actor=actor,
        )

    async def _notify_comment(self, card: KanbanCard, *, body: str, actor: str) -> None:
        """The "I need info" channel (Epic 06 · 6.5): a comment notifies the card's
        assignee and the board owner (reason `participating`); any `@mention`
        notifies the mentioned agent's owner (reason `mention`, which outranks
        participating). The commenter is never notified of their own comment;
        notify_level + per-thread `ignored` still gate delivery."""
        if self._notifications is None:
            return
        actor_uid = await self._resolve_user_id(actor)
        board = await self._boards.get_board(card.board_id)

        # user_id → reason, with `mention` winning over `participating`.
        targets: dict[int, str] = {}

        def _add(uid: int | None, reason: str) -> None:
            if uid is None or uid == actor_uid:
                return
            if uid not in targets or reason == "mention":
                targets[uid] = reason

        _add(await self._resolve_user_id(card.assignee), "participating")
        if board is not None:
            _add(board.owner_id, "participating")
        for slug in parse_mentions(body):
            _add(await self._resolve_user_id(slug), "mention")

        for uid, reason in targets.items():
            await self._notifications.notify(
                uid,
                subject_type="kanban_card",
                subject_key=f"kanban:card:{card.id}",
                reason=reason,
                title=f"Novo comentário no card “{card.title}”",
                link=self._card_link(card),
                actor=actor,
            )

    async def _agent_board(self, agent_slug: str, board_id: int) -> KanbanBoard:
        board = await self._boards.get_board(board_id)
        if board is None:
            raise NotFoundError("Quadro não encontrado.")
        return board

    async def _require_agent_can(
        self, agent_slug: str, board: KanbanBoard, action: str, *, card: KanbanCard | None = None
    ) -> None:
        role = await self.agent_role(board, agent_slug)
        owns = self._agent_owns(card, agent_slug) if card is not None else False
        if not agent_capability(role, action, owns_card=owns):
            raise PermissionDeniedError("Seu agente não tem permissão para esta ação neste quadro.")

    # ---- event-driven cards (hub-side, no MCP — Epic 06 · 6.4/6.5) ----

    # Event-card flags the hub may target (Epic 06 · 6.5). Constrained set — the
    # repo does a getattr, so callers must never pass arbitrary attribute names.
    DELEGATION_FLAG = "auto_card_on_delegation"
    ESCALATION_FLAG = "auto_card_on_escalation"

    async def create_card_for_event(
        self,
        *,
        owner_id: int,
        flag: str,
        title: str,
        body: str,
        assignee: str | None,
        origin: dict,
        priority: str = "normal",
    ) -> KanbanCard | None:
        """Drop an event card on the owner's first board that opted into `flag`
        (delegation/escalation → card, §6.5). Returns None when the owner has no
        opted-in board — the feature is off by default, so most events create
        nothing. The board's observers get a `kanban_delta` like any other card."""
        if flag not in (self.DELEGATION_FLAG, self.ESCALATION_FLAG):
            raise InvalidInputError("Flag de event-card inválida.")
        board = await self._boards.first_board_with_flag(owner_id, flag)
        if board is None:
            return None
        data = CardCreate(title=title, body=body, assignee=assignee, priority=priority)
        return await self.create_event_card(board.id, data, origin=origin, audit_actor="system")

    async def create_event_card(
        self, board_id: int, data: CardCreate, *, origin: dict, audit_actor: str
    ) -> KanbanCard | None:
        """A card the HUB itself opens as a side effect of a trusted event
        (a delegation or escalation, §6.5). Not agent-driven, so it bypasses the
        per-agent capability gate — but it is still fully audited and tagged with
        its `origin`. Returns None if the board vanished (defensive)."""
        board = await self._boards.get_board(board_id)
        if board is None:
            return None
        column = await self._resolve_landing(board_id, data.column_id)
        rank = rank_between(await self._boards.last_rank_in_column(column.id), None)
        card = await self._boards.add_card(
            KanbanCard(
                board_id=board_id,
                column_id=column.id,
                rank=rank,
                title=data.title.strip(),
                body=data.body,
                created_by=audit_actor,
                assignee=data.assignee,
                priority=data.priority,
                origin=origin,
            )
        )
        await self._audit.record(
            "kanban_card_created",
            actor=audit_actor,
            detail={
                "board_id": board_id,
                "card_id": card.id,
                "column_id": column.id,
                "origin": origin,
            },
        )
        return card

    # ---- lifecycle: event card → Done (Epic 07) ----
    #
    # The other half of event cards: when the work an event card represents
    # finishes (a delegation completes, an escalation is resolved), the hub moves
    # the card to a Done column — audited and (like create_event_card) hub-side, so
    # it bypasses the per-agent capability gate but never the dependency gate.

    async def complete_card_for_event(
        self, *, kind: str, ref_id: int, audit_actor: str = "system"
    ) -> KanbanCard | None:
        """Move the card a given event opened to its board's Done column. No-op
        when there is no such card, it is already done, or its dependencies aren't
        met (the Done⇒deps-Done invariant is never broken). Best-effort: callers
        run it after the event's source of truth is already committed."""
        card = await self._boards.card_by_origin_kind_id(kind, ref_id)
        if card is None:
            return None
        return await self._move_card_to_done(card, audit_actor=audit_actor, trigger=kind)

    async def _move_card_to_done(
        self, card: KanbanCard, *, audit_actor: str, trigger: str
    ) -> KanbanCard | None:
        """Move one card to the board's first Done column as the system, reusing
        the race-safe move core. Skips (and audits) a blocked card so a lifecycle
        move can never put an unmet card in Done."""
        current = await self._boards.get_column(card.column_id)
        if current is not None and current.is_done:
            return None  # already finished — idempotent
        done = await self._boards.first_done_column(card.board_id)
        if done is None:
            return None  # board has no terminal column
        if await self._is_blocked(card):
            await self._audit.record(
                "kanban_event_card_done_blocked",
                actor=audit_actor,
                detail={"board_id": card.board_id, "card_id": card.id, "trigger": trigger},
            )
            return None
        moved = await self._move(
            card,
            done.id,
            before_id=None,
            after_id=None,
            expected_version=card.version,
            audit_actor=audit_actor,
        )
        await self._audit.record(
            "kanban_event_card_done",
            actor=audit_actor,
            detail={
                "board_id": moved.board_id,
                "card_id": moved.id,
                "trigger": trigger,
                "origin": moved.origin,
            },
        )
        await self._notify_assignee(moved, reason="state_change", actor=audit_actor)
        return moved

    # ---- dependencies (DAG — Epic 06 · 6.7) ----

    async def _attach_deps(self, board_id: int, cards: list[KanbanCard]) -> None:
        """Set each card's transient `depends_on` from one board-wide query."""
        by_card: dict[int, list[int]] = {}
        for card_id, dep_id in await self._boards.deps_for_board(board_id):
            by_card.setdefault(card_id, []).append(dep_id)
        for card in cards:
            card.depends_on = by_card.get(card.id, [])

    async def _is_blocked(self, card: KanbanCard) -> bool:
        """A card is blocked while any dependency is NOT in a done column."""
        for dep_id in await self._boards.dep_ids_for_card(card.id):
            dep = await self._boards.get_card(dep_id)
            if dep is None:
                continue
            col = await self._boards.get_column(dep.column_id)
            if col is None or not col.is_done:
                return True
        return False

    async def _would_create_cycle(self, board_id: int, card_id: int, depends_on_id: int) -> bool:
        """Adding card_id → depends_on_id closes a cycle iff depends_on_id can
        already reach card_id through existing edges."""
        graph: dict[int, list[int]] = {}
        for a, b in await self._boards.deps_for_board(board_id):
            graph.setdefault(a, []).append(b)
        seen: set[int] = set()
        stack = [depends_on_id]
        while stack:
            node = stack.pop()
            if node == card_id:
                return True
            if node in seen:
                continue
            seen.add(node)
            stack.extend(graph.get(node, []))
        return False

    async def add_dependency(self, user: User, card_id: int, depends_on_id: int) -> None:
        card = await self.get_card(user, card_id)  # 404 + visibility
        if depends_on_id == card_id:
            raise InvalidInputError("Um card não pode depender de si mesmo.")
        dep_card = await self._boards.get_card(depends_on_id)
        if dep_card is None or dep_card.board_id != card.board_id:
            raise InvalidInputError("A dependência deve ser um card do mesmo quadro.")
        if await self._boards.get_dep(card_id, depends_on_id) is not None:
            return  # idempotent
        if await self._would_create_cycle(card.board_id, card_id, depends_on_id):
            raise ConflictError("Isso criaria um ciclo de dependências entre os cards.")
        await self._boards.add_dep(KanbanCardDep(card_id=card_id, depends_on_id=depends_on_id))
        await self._audit.record(
            "kanban_dep_added",
            actor=user.email,
            detail={"card_id": card_id, "depends_on_id": depends_on_id},
        )

    async def remove_dependency(self, user: User, card_id: int, depends_on_id: int) -> None:
        await self.get_card(user, card_id)  # 404 + visibility
        dep = await self._boards.get_dep(card_id, depends_on_id)
        if dep is None:
            return  # idempotent
        await self._boards.remove_dep(dep)
        await self._audit.record(
            "kanban_dep_removed",
            actor=user.email,
            detail={"card_id": card_id, "depends_on_id": depends_on_id},
        )

    async def list_dependencies(self, user: User, card_id: int) -> list[KanbanCard]:
        await self.get_card(user, card_id)  # 404 + visibility
        out: list[KanbanCard] = []
        for dep_id in await self._boards.dep_ids_for_card(card_id):
            dep = await self._boards.get_card(dep_id)
            if dep is not None:
                dep.depends_on = await self._boards.dep_ids_for_card(dep.id)
                out.append(dep)
        return out

    # ---- members (per-user board sharing — Epic 10) ----

    async def list_members(self, user: User, board_id: int) -> list[tuple[KanbanBoardMember, User]]:
        """The board's shared members, enriched with each member's user record.
        Owner/admin only (governance) — a member can see the board but not its
        sharing list."""
        await self._owned_board(user, board_id)
        members = await self._boards.list_members(board_id)
        out: list[tuple[KanbanBoardMember, User]] = []
        for member in members:
            target = await self._users.get_by_id(member.user_id) if self._users else None
            if target is not None:
                out.append((member, target))
        return out

    async def add_member(
        self, user: User, board_id: int, target_user_id: int
    ) -> tuple[KanbanBoardMember, User]:
        """Share a board with a specific person (owner/admin). Idempotent: a repeat
        add returns the existing membership. Audited `kanban_member_added`."""
        await self._owned_board(user, board_id)
        if self._users is None:
            raise InvalidInputError("Gestão de membros indisponível.")
        target = await self._users.get_by_id(target_user_id)
        if target is None:
            raise NotFoundError("Usuário não encontrado.")
        member = await self._boards.get_member(board_id, target_user_id)
        if member is None:
            member = await self._boards.add_member(
                KanbanBoardMember(board_id=board_id, user_id=target_user_id)
            )
            await self._audit.record(
                "kanban_member_added",
                actor=user.email,
                detail={"board_id": board_id, "user_id": target_user_id},
            )
        return member, target

    async def remove_member(self, user: User, board_id: int, target_user_id: int) -> None:
        """Stop sharing the board with a person (owner/admin). Idempotent. Their
        agents' grants are left as-is — revoke those separately if needed. Audited
        `kanban_member_removed`."""
        await self._owned_board(user, board_id)
        member = await self._boards.get_member(board_id, target_user_id)
        if member is None:
            return  # idempotent
        await self._boards.delete_member(member)
        await self._audit.record(
            "kanban_member_removed",
            actor=user.email,
            detail={"board_id": board_id, "user_id": target_user_id},
        )

    # ---- grants & capability (per-agent, per-board — Epic 06 · 6.3 / Epic 10) ----

    async def list_grants(self, user: User, board_id: int) -> list[KanbanAgentGrant]:
        # Any board-visible user may read the grants (so a shared member can manage
        # their own agents' access, Epic 10); writes are still authority-checked.
        await self._visible_board(user, board_id)
        return await self._boards.list_grants(board_id)

    async def set_grant(
        self, user: User, board_id: int, agent_slug: str, role: str
    ) -> KanbanAgentGrant:
        """Grant an agent a role on a board. A privileged action — granting write
        to an AI is treated like relaxing a guardrail: audited as `kanban_grant_set`
        (and behind the danger-zone confirm in the UI, §6.6). Authority (Epic 10):
        the owner/admin may grant ANY agent; any other board-visible user may grant
        only an agent they own."""
        await self._authorize_grant(user, board_id, agent_slug)
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
        await self._authorize_grant(user, board_id, agent_slug)
        grant = await self._boards.get_grant(board_id, agent_slug)
        if grant is None:
            return  # idempotent
        await self._boards.delete_grant(grant)
        await self._audit.record(
            "kanban_grant_removed",
            actor=user.email,
            detail={"board_id": board_id, "agent": agent_slug},
        )

    async def _authorize_grant(self, user: User, board_id: int, agent_slug: str) -> KanbanBoard:
        """Who may grant/revoke a given agent on a board (Epic 10): the owner/admin
        for any agent; any other board-visible user only for an agent they own. A
        404 first (board not visible) never leaks the board's existence."""
        board = await self._visible_board(user, board_id)
        if board.owner_id == user.id or user.role == "admin":
            return board
        agent = await self._agents.get(agent_slug) if self._agents else None
        if agent is None or agent.user_id != user.id:
            raise PermissionDeniedError(
                "Você só pode gerenciar o acesso dos seus próprios agentes."
            )
        return board

    async def agent_role(self, board: KanbanBoard, agent_slug: str) -> str:
        """The agent's effective role on a board: an explicit grant wins; otherwise
        the board's `default_agent_role` — but a non-`team` default only applies to
        agents whose OWNER can see the board (Epic 10). Without that gate, a private
        board with a non-`none` default would be open to every agent of every user,
        broader than "members bring their own agents". `none` = dev-only."""
        grant = await self._boards.get_grant(board.id, agent_slug)
        if grant is not None:
            return grant.role
        if board.default_agent_role == "none":
            return "none"
        if await self._default_role_applies(board, agent_slug):
            return board.default_agent_role
        return "none"

    async def _default_role_applies(self, board: KanbanBoard, agent_slug: str) -> bool:
        """Whether `board.default_agent_role` reaches this agent: always on a `team`
        board; on a private board only when the agent's owner can see it (owner /
        admin / shared member)."""
        if board.visibility == "team":
            return True
        if self._agents is None or self._users is None:
            return False
        agent = await self._agents.get(agent_slug)
        if agent is None:
            return False
        owner = await self._users.get_by_id(agent.user_id)
        return owner is not None and await self._can_see(owner, board)

    @staticmethod
    def _agent_owns(card: KanbanCard, agent_slug: str) -> bool:
        """A contributor's reach: cards it created OR is assigned."""
        return card.created_by == agent_slug or card.assignee == agent_slug

    # ---- internals ----

    def _human_can_see(self, user: User, board: KanbanBoard) -> bool:
        """Cheap, sync visibility: admin, owner, or a team board. A private board
        shared with specific people needs the async membership check (Epic 10)."""
        return user.role == "admin" or board.owner_id == user.id or board.visibility == "team"

    async def _can_see(self, user: User, board: KanbanBoard) -> bool:
        """Full human visibility: the cheap cases, else an explicit board membership
        (a private board shared with this person — Epic 10)."""
        if self._human_can_see(user, board):
            return True
        return await self._boards.is_member(board.id, user.id)

    async def _visible_board(self, user: User, board_id: int) -> KanbanBoard:
        """The board if the human may access it, else 404 (never leak existence)."""
        board = await self._boards.get_board(board_id)
        if board is None or not await self._can_see(user, board):
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
