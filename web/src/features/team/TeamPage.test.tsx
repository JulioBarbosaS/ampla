import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { authApi } from "../../lib/api/auth";
import { usersApi } from "../../lib/api/users";
import { useAuthStore } from "../../stores/auth";
import { TeamPage } from "./TeamPage";

vi.mock("../../lib/api/users", () => ({
  usersApi: { list: vi.fn(), setRole: vi.fn().mockResolvedValue({}) },
}));

vi.mock("../../lib/api/auth", () => ({
  authApi: { listInvites: vi.fn(), createInvite: vi.fn() },
}));

const ADMIN = {
  id: 1,
  email: "admin@example.com",
  name: "Julio",
  role: "admin" as const,
  created_at: "",
};
const MEMBER = {
  id: 2,
  email: "edu@example.com",
  name: "Eduardo",
  role: "member" as const,
  created_at: "",
};

beforeEach(() => {
  useAuthStore.setState({ token: "jwt", user: ADMIN });
  vi.mocked(usersApi.list).mockResolvedValue([ADMIN, MEMBER]);
  vi.mocked(authApi.listInvites).mockResolvedValue([]);
});

afterEach(() => vi.clearAllMocks());

describe("TeamPage", () => {
  it("lista membros com papéis e a ação correta por papel", async () => {
    render(<TeamPage />);
    expect(await screen.findByText("Eduardo")).toBeInTheDocument();
    // membro pode ser promovido; admin pode ser rebaixado
    expect(screen.getByRole("button", { name: "Tornar admin" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rebaixar" })).toBeInTheDocument();
  });

  it("promove um membro a admin", async () => {
    render(<TeamPage />);
    await screen.findByText("Eduardo");
    await userEvent.click(screen.getByRole("button", { name: "Tornar admin" }));
    expect(usersApi.setRole).toHaveBeenCalledWith(2, "admin");
  });

  it("deriva o estado dos convites a partir das datas", async () => {
    vi.mocked(authApi.listInvites).mockResolvedValue([
      {
        id: 1,
        code: "a",
        created_at: "",
        expires_at: "2099-01-01T00:00:00Z",
        used_by: null,
        used_at: null,
      },
      {
        id: 2,
        code: "b",
        created_at: "",
        expires_at: "2020-01-01T00:00:00Z",
        used_by: null,
        used_at: null,
      },
      {
        id: 3,
        code: "c",
        created_at: "",
        expires_at: "2099-01-01T00:00:00Z",
        used_by: 5,
        used_at: "2026-01-01T00:00:00Z",
      },
    ]);
    render(<TeamPage />);
    expect(await screen.findByText("pendente")).toBeInTheDocument();
    expect(screen.getByText("expirado")).toBeInTheDocument();
    expect(screen.getByText("usado")).toBeInTheDocument();
  });

  it("esconde tudo de quem não é admin", () => {
    useAuthStore.setState({ user: MEMBER });
    render(<TeamPage />);
    expect(screen.getByText(/não tem permissão/)).toBeInTheDocument();
    expect(screen.queryByText("Membros da equipe")).not.toBeInTheDocument();
  });
});
