import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../lib/api/client";
import { kanbanApi } from "../../lib/api/kanban";
import type { KanbanBoardFull, KanbanCard } from "../../lib/api/types";
import { BoardPage } from "./BoardPage";

// Keep the real sortColumns/cardsOf helpers; mock only the network methods.
vi.mock("../../lib/api/kanban", async (importActual) => {
  const actual = await importActual<typeof import("../../lib/api/kanban")>();
  return {
    ...actual,
    kanbanApi: {
      listBoards: vi.fn(),
      getBoardFull: vi.fn(),
      createBoard: vi.fn(),
      createCard: vi.fn(),
      moveCard: vi.fn(),
      createColumn: vi.fn(),
      updateColumn: vi.fn(),
      deleteColumn: vi.fn(),
    },
  };
});

vi.mock("../../lib/ws/observer", () => ({ connectObserver: vi.fn(() => () => {}) }));

function card(over: Partial<KanbanCard> = {}): KanbanCard {
  return {
    id: 100,
    board_id: 1,
    column_id: 10,
    rank: "m",
    title: "Card X",
    body: "",
    created_by: "user:1",
    assignee: null,
    priority: "normal",
    origin: null,
    version: 1,
    created_at: "",
    updated_at: "",
    ...over,
  };
}

const FULL: KanbanBoardFull = {
  board: {
    id: 1,
    owner_id: 1,
    name: "Sprint 1",
    visibility: "team",
    default_agent_role: "none",
    auto_card_on_delegation: false,
    auto_card_on_escalation: false,
    created_at: "",
  },
  columns: [
    { id: 10, board_id: 1, name: "A fazer", rank: "a", wip_limit: null, is_landing: true },
    { id: 20, board_id: 1, name: "Fazendo", rank: "b", wip_limit: null, is_landing: false },
  ],
  cards: [card()],
};

beforeEach(() => {
  vi.mocked(kanbanApi.listBoards).mockResolvedValue([FULL.board]);
  vi.mocked(kanbanApi.getBoardFull).mockResolvedValue(structuredClone(FULL));
});

afterEach(() => vi.clearAllMocks());

describe("BoardPage", () => {
  it("renders columns and cards from /full", async () => {
    render(<BoardPage />);
    expect(await screen.findByText("Card X")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "A fazer" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Fazendo" })).toBeInTheDocument();
  });

  it("moves a card with the anchor-based API (destination column + version)", async () => {
    vi.mocked(kanbanApi.moveCard).mockResolvedValue(card({ column_id: 20, version: 2 }));
    render(<BoardPage />);
    await screen.findByText("Card X");
    await userEvent.click(screen.getByRole("button", { name: "Mover Card X para Fazendo" }));
    expect(kanbanApi.moveCard).toHaveBeenCalledWith(100, {
      to_column_id: 20,
      expected_version: 1,
    });
  });

  it("rolls back and refetches on a 409 (stale version)", async () => {
    vi.mocked(kanbanApi.moveCard).mockRejectedValue(new ApiError(409, "conflito"));
    render(<BoardPage />);
    await screen.findByText("Card X");
    await userEvent.click(screen.getByRole("button", { name: "Mover Card X para Fazendo" }));
    // the move was attempted, then the board was refetched to reconcile
    await waitFor(() => expect(kanbanApi.getBoardFull).toHaveBeenCalledTimes(2));
    expect(screen.getByText("Card X")).toBeInTheDocument(); // not lost
  });

  it("creates a card from the landing column", async () => {
    vi.mocked(kanbanApi.createCard).mockResolvedValue(card({ id: 101, title: "Nova" }));
    render(<BoardPage />);
    await screen.findByText("Card X");
    await userEvent.type(screen.getByLabelText("Novo card"), "Nova");
    await userEvent.click(screen.getByRole("button", { name: "+" }));
    expect(kanbanApi.createCard).toHaveBeenCalledWith(1, { title: "Nova" });
  });

  it("creates another board", async () => {
    vi.mocked(kanbanApi.createBoard).mockResolvedValue({ ...FULL.board, id: 2, name: "Outro" });
    render(<BoardPage />);
    await screen.findByText("Card X");
    await userEvent.click(screen.getByRole("button", { name: "+ Novo quadro" }));
    await userEvent.type(screen.getByLabelText("Nome do novo quadro"), "Outro");
    await userEvent.click(screen.getByRole("button", { name: "Criar" }));
    expect(kanbanApi.createBoard).toHaveBeenCalledWith({ name: "Outro" });
  });

  it("adds a custom column", async () => {
    vi.mocked(kanbanApi.createColumn).mockResolvedValue({
      id: 30,
      board_id: 1,
      name: "Bloqueado",
      rank: "z",
      wip_limit: null,
      is_landing: false,
    });
    render(<BoardPage />);
    await screen.findByText("Card X");
    await userEvent.type(screen.getByLabelText("Nova coluna"), "Bloqueado{Enter}");
    expect(kanbanApi.createColumn).toHaveBeenCalledWith(1, { name: "Bloqueado" });
  });

  it("reorders a card within its column via the anchor API", async () => {
    const two: KanbanBoardFull = {
      ...structuredClone(FULL),
      cards: [card({ id: 100, rank: "a" }), card({ id: 101, title: "Card Y", rank: "b" })],
    };
    vi.mocked(kanbanApi.getBoardFull).mockResolvedValue(two);
    vi.mocked(kanbanApi.moveCard).mockResolvedValue(card({ id: 100, rank: "c" }));
    render(<BoardPage />);
    await screen.findByText("Card Y");
    await userEvent.click(screen.getByRole("button", { name: "Descer Card X" }));
    // moving down past Y: lands after Y (before_id=Y, no after) in the same column
    expect(kanbanApi.moveCard).toHaveBeenCalledWith(100, {
      to_column_id: 10,
      before_id: 101,
      expected_version: 1,
    });
  });
});
