import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { kanbanApi } from "../../lib/api/kanban";
import type { KanbanCard } from "../../lib/api/types";
import { CardDetail } from "./CardDetail";

vi.mock("../../lib/api/kanban", () => ({
  kanbanApi: {
    listComments: vi.fn(),
    addComment: vi.fn(),
    updateCard: vi.fn(),
    deleteCard: vi.fn(),
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
  vi.mocked(kanbanApi.updateCard).mockResolvedValue(card({ title: "editado" }));
  vi.mocked(kanbanApi.deleteCard).mockResolvedValue(undefined);
});

afterEach(() => vi.clearAllMocks());

describe("CardDetail", () => {
  it("renders editable fields, body and existing comments", async () => {
    render(<CardDetail card={card()} onClose={vi.fn()} onChanged={vi.fn()} />);
    expect(screen.getByRole("dialog", { name: /Implementar OAuth/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Título")).toHaveValue("Implementar OAuth");
    expect(screen.getByLabelText("Responsável")).toHaveValue("backend-ana");
    expect(screen.getByLabelText("Descrição")).toHaveValue("corpo do card");
    expect(await screen.findByText("primeiro comentario")).toBeInTheDocument();
  });

  it("saves edits with the optimistic version", async () => {
    const onChanged = vi.fn();
    render(<CardDetail card={card()} onClose={vi.fn()} onChanged={onChanged} />);
    await userEvent.clear(screen.getByLabelText("Título"));
    await userEvent.type(screen.getByLabelText("Título"), "Novo título");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(kanbanApi.updateCard).toHaveBeenCalledWith(7, {
      title: "Novo título",
      body: "corpo do card",
      priority: "high",
      assignee: "backend-ana",
      expected_version: 1,
    });
    expect(onChanged).toHaveBeenCalled();
  });

  it("deletes the card and signals removal", async () => {
    const onChanged = vi.fn();
    const onClose = vi.fn();
    render(<CardDetail card={card()} onClose={onClose} onChanged={onChanged} />);
    await userEvent.click(screen.getByRole("button", { name: "Excluir card" }));
    expect(kanbanApi.deleteCard).toHaveBeenCalledWith(7);
    expect(onChanged).toHaveBeenCalledWith(null);
  });

  it("posts a comment and appends it", async () => {
    render(<CardDetail card={card()} onClose={vi.fn()} onChanged={vi.fn()} />);
    await screen.findByText("primeiro comentario");
    await userEvent.type(screen.getByLabelText("Novo comentário"), "novo");
    await userEvent.click(screen.getByRole("button", { name: "Comentar" }));
    expect(kanbanApi.addComment).toHaveBeenCalledWith(7, "novo");
    expect(await screen.findByText("novo")).toBeInTheDocument();
  });

  it("closes via the close button", async () => {
    const onClose = vi.fn();
    render(<CardDetail card={card()} onClose={onClose} onChanged={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(onClose).toHaveBeenCalled();
  });
});
