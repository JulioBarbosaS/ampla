import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { kanbanApi } from "../../lib/api/kanban";
import type { KanbanCard } from "../../lib/api/types";
import { CardDetail } from "./CardDetail";

vi.mock("../../lib/api/kanban", () => ({
  kanbanApi: {
    listComments: vi.fn(),
    addComment: vi.fn(),
  },
}));

function card(over: Partial<KanbanCard> = {}): KanbanCard {
  return {
    id: 7,
    board_id: 1,
    column_id: 10,
    rank: "m",
    title: "Implementar OAuth",
    body: "corpo do card",
    created_by: "user:1",
    assignee: "backend-ana",
    priority: "high",
    origin: null,
    version: 1,
    created_at: "",
    updated_at: "",
    ...over,
  };
}

beforeEach(() => {
  vi.mocked(kanbanApi.listComments).mockResolvedValue([
    { id: 1, card_id: 7, author: "user:1", body: "primeiro comentario", created_at: "" },
  ]);
  vi.mocked(kanbanApi.addComment).mockResolvedValue({
    id: 2,
    card_id: 7,
    author: "user:1",
    body: "novo",
    created_at: "",
  });
});

afterEach(() => vi.clearAllMocks());

describe("CardDetail", () => {
  it("renders the title, body and existing comments", async () => {
    render(<CardDetail card={card()} onClose={vi.fn()} />);
    expect(screen.getByRole("dialog", { name: /Implementar OAuth/ })).toBeInTheDocument();
    expect(screen.getByText("corpo do card")).toBeInTheDocument();
    expect(await screen.findByText("primeiro comentario")).toBeInTheDocument();
    expect(screen.getByText(/Responsável: backend-ana/)).toBeInTheDocument();
  });

  it("posts a comment and appends it", async () => {
    render(<CardDetail card={card()} onClose={vi.fn()} />);
    await screen.findByText("primeiro comentario");
    await userEvent.type(screen.getByLabelText("Novo comentário"), "novo");
    await userEvent.click(screen.getByRole("button", { name: "Comentar" }));
    expect(kanbanApi.addComment).toHaveBeenCalledWith(7, "novo");
    expect(await screen.findByText("novo")).toBeInTheDocument();
  });

  it("closes via the close button", async () => {
    const onClose = vi.fn();
    render(<CardDetail card={card()} onClose={onClose} />);
    await userEvent.click(screen.getByRole("button", { name: "Fechar" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});
