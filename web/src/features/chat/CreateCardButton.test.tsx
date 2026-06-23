import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { kanbanApi } from "../../lib/api/kanban";
import type { KanbanBoard } from "../../lib/api/types";
import { CreateCardButton } from "./CreateCardButton";

vi.mock("../../lib/api/kanban", () => ({
  kanbanApi: { listBoards: vi.fn(), createCard: vi.fn() },
}));

const board: KanbanBoard = {
  id: 3,
  owner_id: 1,
  name: "Sprint",
  visibility: "team",
  default_agent_role: "none",
  auto_card_on_delegation: false,
  auto_card_on_escalation: false,
  created_at: "",
};

beforeEach(() => {
  vi.mocked(kanbanApi.listBoards).mockResolvedValue([board]);
  vi.mocked(kanbanApi.createCard).mockResolvedValue({ id: 1 } as never);
});

afterEach(() => vi.clearAllMocks());

describe("CreateCardButton", () => {
  it("creates a card from the conversation with a message origin", async () => {
    render(<CreateCardButton partner="mobile-ana" lastMessageId={42} />);
    await userEvent.click(screen.getByRole("button", { name: "Criar card" }));
    expect(await screen.findByLabelText("Título do card")).toHaveValue("Conversa com mobile-ana");
    await userEvent.click(screen.getByRole("button", { name: "Criar" }));
    expect(kanbanApi.createCard).toHaveBeenCalledWith(3, {
      title: "Conversa com mobile-ana",
      origin: { kind: "message", id: 42 },
    });
  });

  it("omits the origin when there is no message yet", async () => {
    render(<CreateCardButton partner="mobile-ana" lastMessageId={null} />);
    await userEvent.click(screen.getByRole("button", { name: "Criar card" }));
    await screen.findByLabelText("Quadro de destino");
    await userEvent.click(screen.getByRole("button", { name: "Criar" }));
    expect(kanbanApi.createCard).toHaveBeenCalledWith(3, { title: "Conversa com mobile-ana" });
  });
});
