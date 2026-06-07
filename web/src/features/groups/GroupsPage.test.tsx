import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { groupsApi } from "../../lib/api/groups";
import { useAuthStore } from "../../stores/auth";
import { GroupsPage } from "./GroupsPage";

vi.mock("../../lib/api/groups", () => ({
  groupsApi: {
    list: vi.fn(),
    create: vi.fn().mockResolvedValue({}),
    remove: vi.fn().mockResolvedValue(undefined),
    addMember: vi.fn().mockResolvedValue(undefined),
    removeMember: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock("../../lib/api/agents", () => ({
  agentsApi: {
    directory: vi.fn().mockResolvedValue([
      { slug: "backend-julio", display_name: "Backend", online: true },
      { slug: "mobile-eduardo", display_name: "Mobile", online: true },
      { slug: "infra-maria", display_name: "Infra", online: false },
    ]),
    mine: vi.fn().mockResolvedValue([
      {
        slug: "backend-julio",
        user_id: 1,
        display_name: "Backend",
        created_at: "",
        mode: "inbox",
        allowed_senders: null,
        max_auto_per_hour: 10,
        auto_timeout_secs: 120,
        instructions: "",
      },
    ]),
  },
}));

beforeEach(() => {
  useAuthStore.setState({
    token: "jwt",
    user: { id: 1, email: "j@example.com", name: "Julio", role: "member", created_at: "" },
  });
  vi.mocked(groupsApi.list).mockResolvedValue([
    {
      slug: "frontend-team",
      display_name: "Time Frontend",
      created_by: 1,
      created_at: "",
      members: ["mobile-eduardo"],
    },
  ]);
});

afterEach(() => vi.clearAllMocks());

describe("GroupsPage", () => {
  it("lista grupos com membros e presença", async () => {
    render(<GroupsPage />);
    expect(await screen.findByText("@frontend-team")).toBeInTheDocument();
    expect(screen.getByText("mobile-eduardo")).toBeInTheDocument();
    expect(screen.getByText(/Membros \(1\)/)).toBeInTheDocument();
  });

  it("só permite adicionar os próprios agentes (outros desabilitados)", async () => {
    render(<GroupsPage />);
    await screen.findByText("@frontend-team");
    // backend-julio é meu → habilitado; infra-maria é de outro → desabilitado
    expect(screen.getByRole("button", { name: "+ backend-julio" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "+ infra-maria" })).toBeDisabled();
  });

  it("adiciona um agente próprio ao grupo", async () => {
    render(<GroupsPage />);
    await screen.findByText("@frontend-team");
    await userEvent.click(screen.getByRole("button", { name: "+ backend-julio" }));
    expect(groupsApi.addMember).toHaveBeenCalledWith("frontend-team", "backend-julio");
  });

  it("cria um grupo", async () => {
    render(<GroupsPage />);
    await screen.findByText("@frontend-team");
    await userEvent.type(screen.getByLabelText(/Slug/), "infra-team");
    await userEvent.type(screen.getByLabelText(/Nome de exibição/), "Infra");
    await userEvent.click(screen.getByRole("button", { name: "Criar" }));
    expect(groupsApi.create).toHaveBeenCalledWith({
      slug: "infra-team",
      display_name: "Infra",
    });
  });
});
