import { api } from "./client";
import type {
  KanbanBoard,
  KanbanBoardFull,
  KanbanCard,
  KanbanColumn,
  KanbanComment,
  KanbanGrant,
} from "./types";

/** Anchor-based move intent (Epic 06 · 6.2): the server recomputes the rank from
 * the current neighbours and rejects a stale `expected_version` with 409. */
export interface MoveCardInput {
  to_column_id: number;
  before_id?: number;
  after_id?: number;
  expected_version: number;
}

export const kanbanApi = {
  listBoards: () => api.get<KanbanBoard[]>("/api/kanban/boards"),
  createBoard: (data: { name: string; visibility?: string; default_agent_role?: string }) =>
    api.post<KanbanBoard>("/api/kanban/boards", data),
  getBoardFull: (boardId: number) => api.get<KanbanBoardFull>(`/api/kanban/boards/${boardId}/full`),
  updateBoard: (
    boardId: number,
    data: { name?: string; visibility?: string; default_agent_role?: string },
  ) => api.patch<KanbanBoard>(`/api/kanban/boards/${boardId}`, data),
  deleteBoard: (boardId: number) => api.delete<void>(`/api/kanban/boards/${boardId}`),

  createCard: (
    boardId: number,
    data: {
      title: string;
      body?: string;
      column_id?: number;
      assignee?: string;
      priority?: string;
    },
  ) => api.post<KanbanCard>(`/api/kanban/boards/${boardId}/cards`, data),
  updateCard: (
    cardId: number,
    data: {
      title?: string;
      body?: string;
      assignee?: string;
      clear_assignee?: boolean;
      priority?: string;
      expected_version?: number;
    },
  ) => api.patch<KanbanCard>(`/api/kanban/cards/${cardId}`, data),
  moveCard: (cardId: number, data: MoveCardInput) =>
    api.post<KanbanCard>(`/api/kanban/cards/${cardId}/move`, data),
  deleteCard: (cardId: number) => api.delete<void>(`/api/kanban/cards/${cardId}`),

  listComments: (cardId: number) =>
    api.get<KanbanComment[]>(`/api/kanban/cards/${cardId}/comments`),
  addComment: (cardId: number, body: string) =>
    api.post<KanbanComment>(`/api/kanban/cards/${cardId}/comments`, { body }),

  // grants (owner/admin) — danger-zone for agent write lives in the UI (6.6)
  listGrants: (boardId: number) => api.get<KanbanGrant[]>(`/api/kanban/boards/${boardId}/grants`),
  setGrant: (boardId: number, agent_slug: string, role: string) =>
    api.put<KanbanGrant>(`/api/kanban/boards/${boardId}/grants`, { agent_slug, role }),
  removeGrant: (boardId: number, agentSlug: string) =>
    api.delete<void>(`/api/kanban/boards/${boardId}/grants/${encodeURIComponent(agentSlug)}`),
};

/** Columns sorted left→right by rank (the server's ordering). */
export function sortColumns(columns: KanbanColumn[]): KanbanColumn[] {
  return [...columns].sort((a, b) => (a.rank < b.rank ? -1 : a.rank > b.rank ? 1 : 0));
}

/** Cards of one column, sorted top→bottom by rank. */
export function cardsOf(cards: KanbanCard[], columnId: number): KanbanCard[] {
  return cards
    .filter((c) => c.column_id === columnId)
    .sort((a, b) => (a.rank < b.rank ? -1 : a.rank > b.rank ? 1 : 0));
}
