import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { kanbanApi } from "../../lib/api/kanban";
import type { KanbanBoard } from "../../lib/api/types";
import { BoardSettings } from "./BoardSettings";

vi.mock("../../lib/api/kanban", () => ({
  kanbanApi: {
    listGrants: vi.fn(),
    setGrant: vi.fn().mockResolvedValue({}),
    removeGrant: vi.fn().mockResolvedValue(undefined),
    updateBoard: vi.fn(),
    deleteBoard: vi.fn().mockResolvedValue(undefined),
  },
}));

const BOARD: KanbanBoard = {
  id: 1,
  owner_id: 1,
  name: "Sprint 1",
  visibility: "team",
  default_agent_role: "none",
  auto_card_on_delegation: false,
  auto_card_on_escalation: false,
  created_at: "",
};

function renderSettings(overrides: { onBoardDeleted?: () => void } = {}) {
  return render(
    <BoardSettings
      board={BOARD}
      onBoardChange={vi.fn()}
      onBoardDeleted={overrides.onBoardDeleted ?? vi.fn()}
    />,
  );
}

vi.mock("../../lib/api/agents", () => ({
  agentsApi: {
    directory: vi.fn().mockResolvedValue([
      { slug: "backend-ana", display_name: "Ana", online: true },
      { slug: "mobile-edu", display_name: "Edu", online: false },
    ]),
  },
}));

beforeEach(() => {
  vi.mocked(kanbanApi.listGrants).mockResolvedValue([]);
});

afterEach(() => vi.clearAllMocks());

describe("BoardSettings (grants + danger-zone)", () => {
  it("lists current grants with their role", async () => {
    vi.mocked(kanbanApi.listGrants).mockResolvedValue([
      { board_id: 1, agent_slug: "backend-ana", role: "editor" },
    ]);
    renderSettings();
    const item = (await screen.findByText("backend-ana")).closest("li");
    // scope to the grant row — "Editor" also appears as a role <select> option
    expect(within(item as HTMLElement).getByText("Editor")).toBeInTheDocument();
  });

  it("grants a viewer role directly (no danger-zone)", async () => {
    renderSettings();
    await screen.findByText(/só para devs/i);
    await userEvent.selectOptions(screen.getByLabelText("Agente"), "backend-ana");
    // role defaults to viewer → a plain "Conceder" button, no confirmation
    await userEvent.click(screen.getByRole("button", { name: "Conceder" }));
    expect(kanbanApi.setGrant).toHaveBeenCalledWith(1, "backend-ana", "viewer");
  });

  it("granting write (editor) goes through the danger-zone confirm", async () => {
    renderSettings();
    await screen.findByText(/só para devs/i);
    await userEvent.selectOptions(screen.getByLabelText("Agente"), "backend-ana");
    await userEvent.selectOptions(screen.getByLabelText("Papel"), "editor");
    // no plain Conceder button for a write role
    expect(screen.queryByRole("button", { name: "Conceder" })).not.toBeInTheDocument();
    // walk the danger-zone: warn → reconfirm → type the slug → apply
    await userEvent.click(screen.getByRole("button", { name: /Conceder Editor a backend-ana/ }));
    await userEvent.click(screen.getByRole("button", { name: "Entendo o risco" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirmar de novo" }));
    await userEvent.type(screen.getByPlaceholderText("backend-ana"), "backend-ana");
    await userEvent.click(screen.getByRole("button", { name: "Aplicar" }));
    expect(kanbanApi.setGrant).toHaveBeenCalledWith(1, "backend-ana", "editor");
  });

  it("revokes a grant", async () => {
    vi.mocked(kanbanApi.listGrants).mockResolvedValue([
      { board_id: 1, agent_slug: "backend-ana", role: "viewer" },
    ]);
    renderSettings();
    await userEvent.click(
      await screen.findByRole("button", { name: "Remover acesso de backend-ana" }),
    );
    await waitFor(() => expect(kanbanApi.removeGrant).toHaveBeenCalledWith(1, "backend-ana"));
  });

  it("toggles the opt-in event-card flag", async () => {
    vi.mocked(kanbanApi.updateBoard).mockResolvedValue({ ...BOARD, auto_card_on_delegation: true });
    renderSettings();
    await userEvent.click(await screen.findByLabelText(/quando uma tarefa for delegada/i));
    expect(kanbanApi.updateBoard).toHaveBeenCalledWith(1, { auto_card_on_delegation: true });
  });

  it("changes board visibility and default agent role", async () => {
    vi.mocked(kanbanApi.updateBoard).mockResolvedValue(BOARD);
    renderSettings();
    await userEvent.selectOptions(await screen.findByLabelText("Visibilidade"), "private");
    expect(kanbanApi.updateBoard).toHaveBeenCalledWith(1, { visibility: "private" });
    await userEvent.selectOptions(screen.getByLabelText("Papel padrão dos agentes"), "viewer");
    expect(kanbanApi.updateBoard).toHaveBeenCalledWith(1, { default_agent_role: "viewer" });
  });

  it("deletes the board through the danger-zone", async () => {
    const onBoardDeleted = vi.fn();
    renderSettings({ onBoardDeleted });
    await userEvent.click(await screen.findByRole("button", { name: "Excluir este quadro" }));
    await userEvent.click(screen.getByRole("button", { name: "Entendo o risco" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirmar de novo" }));
    await userEvent.type(screen.getByPlaceholderText("Sprint 1"), "Sprint 1");
    await userEvent.click(screen.getByRole("button", { name: "Aplicar" }));
    expect(kanbanApi.deleteBoard).toHaveBeenCalledWith(1);
    await waitFor(() => expect(onBoardDeleted).toHaveBeenCalled());
  });
});
