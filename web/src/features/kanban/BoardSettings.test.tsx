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
    listMembers: vi.fn(),
    addMember: vi.fn().mockResolvedValue({}),
    removeMember: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock("../../lib/api/users", () => ({
  usersApi: {
    list: vi.fn().mockResolvedValue([
      { id: 1, email: "owner@amp.local", name: "Owner", role: "admin", created_at: "" },
      { id: 2, email: "joao@amp.local", name: "João", role: "member", created_at: "" },
    ]),
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

function renderSettings(overrides: { onBoardDeleted?: () => void; canManage?: boolean } = {}) {
  return render(
    <BoardSettings
      board={BOARD}
      onBoardChange={vi.fn()}
      onBoardDeleted={overrides.onBoardDeleted ?? vi.fn()}
      canManage={overrides.canManage ?? true}
    />,
  );
}

vi.mock("../../lib/api/agents", () => ({
  agentsApi: {
    directory: vi.fn().mockResolvedValue([
      { slug: "backend-ana", display_name: "Ana", online: true },
      { slug: "mobile-edu", display_name: "Edu", online: false },
    ]),
    mine: vi.fn().mockResolvedValue([{ slug: "backend-ana", display_name: "Ana" }]),
  },
}));

beforeEach(() => {
  vi.mocked(kanbanApi.listGrants).mockResolvedValue([]);
  vi.mocked(kanbanApi.listMembers).mockResolvedValue([]);
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

describe("BoardSettings · members (Epic 10)", () => {
  it("owner shares the board with a specific person", async () => {
    renderSettings({ canManage: true });
    // the owner (id 1) is excluded from the picker; João (id 2) is addable
    await userEvent.selectOptions(await screen.findByLabelText("Pessoa"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Adicionar" }));
    expect(kanbanApi.addMember).toHaveBeenCalledWith(1, 2);
  });

  it("owner removes a member", async () => {
    vi.mocked(kanbanApi.listMembers).mockResolvedValue([
      { board_id: 1, user_id: 2, name: "João", email: "joao@amp.local", created_at: "" },
    ]);
    renderSettings({ canManage: true });
    await userEvent.click(await screen.findByRole("button", { name: "Remover João do quadro" }));
    await waitFor(() => expect(kanbanApi.removeMember).toHaveBeenCalledWith(1, 2));
  });
});

describe("BoardSettings · member-limited panel (Epic 10)", () => {
  it("hides governance (visibility, members, danger-zone) for a non-owner", async () => {
    renderSettings({ canManage: false });
    await screen.findByText(/seus próprios agentes/i);
    expect(screen.queryByLabelText("Visibilidade")).not.toBeInTheDocument();
    expect(screen.queryByText("Membros do quadro")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Excluir este quadro" })).not.toBeInTheDocument();
  });

  it("limits the grant picker to the member's own agents", async () => {
    renderSettings({ canManage: false });
    const picker = await screen.findByLabelText("Agente");
    // own agent present; a directory-only agent (mobile-edu) is not offered
    expect(within(picker as HTMLElement).getByRole("option", { name: "backend-ana" })).toBeTruthy();
    expect(
      within(picker as HTMLElement).queryByRole("option", { name: "mobile-edu" }),
    ).not.toBeInTheDocument();
    await userEvent.selectOptions(picker, "backend-ana");
    await userEvent.click(screen.getByRole("button", { name: "Conceder" }));
    expect(kanbanApi.setGrant).toHaveBeenCalledWith(1, "backend-ana", "viewer");
  });

  it("a member cannot revoke another user's agent grant", async () => {
    vi.mocked(kanbanApi.listGrants).mockResolvedValue([
      { board_id: 1, agent_slug: "backend-ana", role: "viewer" }, // own → revocable
      { board_id: 1, agent_slug: "maria-front", role: "viewer" }, // not own → no button
    ]);
    renderSettings({ canManage: false });
    expect(
      await screen.findByRole("button", { name: "Remover acesso de backend-ana" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Remover acesso de maria-front" }),
    ).not.toBeInTheDocument();
  });
});
