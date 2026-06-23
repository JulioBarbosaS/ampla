import { api } from "./client";
import type {
  KanbanBoard,
  KanbanBoardFull,
  KanbanCard,
  KanbanCardOrigin,
  KanbanColumn,
  KanbanComment,
  KanbanGrant,
  KanbanMember,
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

  createColumn: (boardId: number, data: { name: string; wip_limit?: number }) =>
    api.post<KanbanColumn>(`/api/kanban/boards/${boardId}/columns`, data),
  updateColumn: (
    boardId: number,
    columnId: number,
    data: { name?: string; wip_limit?: number; is_landing?: boolean; is_done?: boolean },
  ) => api.patch<KanbanColumn>(`/api/kanban/boards/${boardId}/columns/${columnId}`, data),
  deleteColumn: (boardId: number, columnId: number) =>
    api.delete<void>(`/api/kanban/boards/${boardId}/columns/${columnId}`),

  createCard: (
    boardId: number,
    data: {
      title: string;
      body?: string;
      column_id?: number;
      assignee?: string;
      priority?: string;
      // Provenance (Epic 07): clients may set message/thread origins only.
      origin?: { kind: "message" | "thread"; id: number };
    },
  ) => api.post<KanbanCard>(`/api/kanban/boards/${boardId}/cards`, data),

  // Resolve a card's origin to a deep-link to its source conversation (Epic 07).
  getCardOrigin: (cardId: number) =>
    api.get<KanbanCardOrigin>(`/api/kanban/cards/${cardId}/origin`),
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

  // dependencies (DAG — Epic 06 · 6.7): returns the updated "blocked by" set
  listDependencies: (cardId: number) =>
    api.get<KanbanCard[]>(`/api/kanban/cards/${cardId}/dependencies`),
  addDependency: (cardId: number, dependsOnId: number) =>
    api.post<KanbanCard[]>(`/api/kanban/cards/${cardId}/dependencies`, {
      depends_on_id: dependsOnId,
    }),
  removeDependency: (cardId: number, dependsOnId: number) =>
    api.delete<void>(`/api/kanban/cards/${cardId}/dependencies/${dependsOnId}`),

  listComments: (cardId: number) =>
    api.get<KanbanComment[]>(`/api/kanban/cards/${cardId}/comments`),
  addComment: (cardId: number, body: string) =>
    api.post<KanbanComment>(`/api/kanban/cards/${cardId}/comments`, { body }),

  // grants: owner/admin may grant any agent; a board-visible member may grant
  // their OWN agents (Epic 10). Danger-zone for agent write lives in the UI (6.6).
  listGrants: (boardId: number) => api.get<KanbanGrant[]>(`/api/kanban/boards/${boardId}/grants`),
  setGrant: (boardId: number, agent_slug: string, role: string) =>
    api.put<KanbanGrant>(`/api/kanban/boards/${boardId}/grants`, { agent_slug, role }),
  removeGrant: (boardId: number, agentSlug: string) =>
    api.delete<void>(`/api/kanban/boards/${boardId}/grants/${encodeURIComponent(agentSlug)}`),

  // members (per-user board sharing — Epic 10). Management is owner/admin only.
  listMembers: (boardId: number) =>
    api.get<KanbanMember[]>(`/api/kanban/boards/${boardId}/members`),
  addMember: (boardId: number, userId: number) =>
    api.post<KanbanMember>(`/api/kanban/boards/${boardId}/members`, { user_id: userId }),
  removeMember: (boardId: number, userId: number) =>
    api.delete<void>(`/api/kanban/boards/${boardId}/members/${userId}`),
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
