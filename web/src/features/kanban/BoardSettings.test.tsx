import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { kanbanApi } from "../../lib/api/kanban";
import { BoardSettings } from "./BoardSettings";

vi.mock("../../lib/api/kanban", () => ({
  kanbanApi: {
    listGrants: vi.fn(),
    setGrant: vi.fn().mockResolvedValue({}),
    removeGrant: vi.fn().mockResolvedValue(undefined),
  },
}));

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
    render(<BoardSettings boardId={1} />);
    const item = (await screen.findByText("backend-ana")).closest("li");
    // scope to the grant row — "Editor" also appears as a role <select> option
    expect(within(item as HTMLElement).getByText("Editor")).toBeInTheDocument();
  });

  it("grants a viewer role directly (no danger-zone)", async () => {
    render(<BoardSettings boardId={1} />);
    await screen.findByText(/só para devs/i);
    await userEvent.selectOptions(screen.getByLabelText("Agente"), "backend-ana");
    // role defaults to viewer → a plain "Conceder" button, no confirmation
    await userEvent.click(screen.getByRole("button", { name: "Conceder" }));
    expect(kanbanApi.setGrant).toHaveBeenCalledWith(1, "backend-ana", "viewer");
  });

  it("granting write (editor) goes through the danger-zone confirm", async () => {
    render(<BoardSettings boardId={1} />);
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
    render(<BoardSettings boardId={1} />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Remover acesso de backend-ana" }),
    );
    await waitFor(() => expect(kanbanApi.removeGrant).toHaveBeenCalledWith(1, "backend-ana"));
  });
});
