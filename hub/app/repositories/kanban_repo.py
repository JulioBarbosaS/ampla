"""Data access for the Kanban board (Epic 06). Pure persistence — no authz,
no ordering algebra (that lives in KanbanService / kanban_rank). Writes commit
so each mutation is its own serialized transaction (SQLite serializes writers,
the pessimistic lock the move path relies on, Epic 06 · 6.2)."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kanban import (
    KanbanAgentGrant,
    KanbanBoard,
    KanbanCard,
    KanbanCardComment,
    KanbanColumn,
)


class KanbanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ---- boards ----

    async def add_board(self, board: KanbanBoard) -> KanbanBoard:
        self._session.add(board)
        await self._session.commit()
        await self._session.refresh(board)
        return board

    async def get_board(self, board_id: int) -> KanbanBoard | None:
        return await self._session.get(KanbanBoard, board_id)

    async def list_visible_boards(self, user_id: int, *, is_admin: bool) -> list[KanbanBoard]:
        stmt = select(KanbanBoard)
        if not is_admin:
            # Own boards + every team-visible board (private boards stay hidden).
            stmt = stmt.where(
                or_(KanbanBoard.owner_id == user_id, KanbanBoard.visibility == "team")
            )
        stmt = stmt.order_by(KanbanBoard.created_at.desc(), KanbanBoard.id.desc())
        return list((await self._session.execute(stmt)).scalars())

    async def save_board(self, board: KanbanBoard) -> None:
        self._session.add(board)
        await self._session.commit()

    async def delete_board(self, board: KanbanBoard) -> None:
        # Children first (FK order); cheap at a local board's scale.
        await self._session.execute(
            KanbanCardComment.__table__.delete().where(
                KanbanCardComment.card_id.in_(
                    select(KanbanCard.id).where(KanbanCard.board_id == board.id)
                )
            )
        )
        await self._session.execute(
            KanbanCard.__table__.delete().where(KanbanCard.board_id == board.id)
        )
        await self._session.execute(
            KanbanColumn.__table__.delete().where(KanbanColumn.board_id == board.id)
        )
        await self._session.execute(
            KanbanAgentGrant.__table__.delete().where(KanbanAgentGrant.board_id == board.id)
        )
        await self._session.delete(board)
        await self._session.commit()

    # ---- columns ----

    async def add_column(self, column: KanbanColumn) -> KanbanColumn:
        self._session.add(column)
        await self._session.commit()
        await self._session.refresh(column)
        return column

    async def add_columns(self, columns: list[KanbanColumn]) -> None:
        """Bulk insert in one transaction (used to seed a board's defaults)."""
        self._session.add_all(columns)
        await self._session.commit()

    async def get_column(self, column_id: int) -> KanbanColumn | None:
        return await self._session.get(KanbanColumn, column_id)

    async def list_columns(self, board_id: int) -> list[KanbanColumn]:
        stmt = (
            select(KanbanColumn)
            .where(KanbanColumn.board_id == board_id)
            .order_by(KanbanColumn.rank)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def landing_column(self, board_id: int) -> KanbanColumn | None:
        stmt = (
            select(KanbanColumn)
            .where(KanbanColumn.board_id == board_id, KanbanColumn.is_landing.is_(True))
            .order_by(KanbanColumn.rank)
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def save_column(self, column: KanbanColumn) -> None:
        self._session.add(column)
        await self._session.commit()

    async def clear_landing(self, board_id: int) -> None:
        """Drop the landing flag from every column (before setting a new one)."""
        await self._session.execute(
            KanbanColumn.__table__.update()
            .where(KanbanColumn.board_id == board_id)
            .values(is_landing=False)
        )
        await self._session.commit()

    async def delete_column(self, column: KanbanColumn) -> None:
        await self._session.delete(column)
        await self._session.commit()

    # ---- cards ----

    async def add_card(self, card: KanbanCard) -> KanbanCard:
        self._session.add(card)
        await self._session.commit()
        await self._session.refresh(card)
        return card

    async def get_card(self, card_id: int) -> KanbanCard | None:
        return await self._session.get(KanbanCard, card_id)

    async def list_cards(self, board_id: int) -> list[KanbanCard]:
        stmt = (
            select(KanbanCard)
            .where(KanbanCard.board_id == board_id)
            .order_by(KanbanCard.column_id, KanbanCard.rank)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def list_cards_in_column(self, column_id: int) -> list[KanbanCard]:
        stmt = select(KanbanCard).where(KanbanCard.column_id == column_id).order_by(KanbanCard.rank)
        return list((await self._session.execute(stmt)).scalars())

    async def count_cards_in_column(self, column_id: int) -> int:
        stmt = select(func.count()).select_from(KanbanCard).where(KanbanCard.column_id == column_id)
        return int((await self._session.execute(stmt)).scalar_one())

    async def last_rank_in_column(self, column_id: int) -> str | None:
        """The greatest rank in a column (to append a new card after it)."""
        stmt = (
            select(KanbanCard.rank)
            .where(KanbanCard.column_id == column_id)
            .order_by(KanbanCard.rank.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def save_card(self, card: KanbanCard) -> None:
        self._session.add(card)
        await self._session.commit()

    async def delete_card(self, card: KanbanCard) -> None:
        await self._session.execute(
            KanbanCardComment.__table__.delete().where(KanbanCardComment.card_id == card.id)
        )
        await self._session.delete(card)
        await self._session.commit()

    # ---- comments ----

    async def add_comment(self, comment: KanbanCardComment) -> KanbanCardComment:
        self._session.add(comment)
        await self._session.commit()
        await self._session.refresh(comment)
        return comment

    async def list_comments(self, card_id: int) -> list[KanbanCardComment]:
        stmt = (
            select(KanbanCardComment)
            .where(KanbanCardComment.card_id == card_id)
            .order_by(KanbanCardComment.created_at, KanbanCardComment.id)
        )
        return list((await self._session.execute(stmt)).scalars())

    # ---- grants (per-agent, per-board — Epic 06 · 6.3) ----

    async def get_grant(self, board_id: int, agent_slug: str) -> KanbanAgentGrant | None:
        stmt = select(KanbanAgentGrant).where(
            KanbanAgentGrant.board_id == board_id,
            KanbanAgentGrant.agent_slug == agent_slug,
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def list_grants(self, board_id: int) -> list[KanbanAgentGrant]:
        stmt = (
            select(KanbanAgentGrant)
            .where(KanbanAgentGrant.board_id == board_id)
            .order_by(KanbanAgentGrant.agent_slug)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def add_grant(self, grant: KanbanAgentGrant) -> KanbanAgentGrant:
        self._session.add(grant)
        await self._session.commit()
        await self._session.refresh(grant)
        return grant

    async def save_grant(self, grant: KanbanAgentGrant) -> None:
        self._session.add(grant)
        await self._session.commit()

    async def delete_grant(self, grant: KanbanAgentGrant) -> None:
        await self._session.delete(grant)
        await self._session.commit()
