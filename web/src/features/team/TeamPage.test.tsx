import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { adminApi } from "../../lib/api/admin";
import { authApi } from "../../lib/api/auth";
import { usersApi } from "../../lib/api/users";
import { useAuthStore } from "../../stores/auth";
import { useKillSwitchStore } from "../../stores/killSwitch";
import { TeamPage } from "./TeamPage";

vi.mock("../../lib/api/users", () => ({
  usersApi: { list: vi.fn(), setRole: vi.fn().mockResolvedValue({}), auditLog: vi.fn() },
}));

vi.mock("../../lib/api/auth", () => ({
  authApi: { listInvites: vi.fn(), createInvite: vi.fn() },
}));

vi.mock("../../lib/api/admin", () => ({
  adminApi: { getKillSwitch: vi.fn(), setKillSwitch: vi.fn(), autorespondRuns: vi.fn() },
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
  useAuthStore.setState({ user: ADMIN });
  useKillSwitchStore.setState({ autoResponderEnabled: true });
  vi.mocked(usersApi.list).mockResolvedValue([ADMIN, MEMBER]);
  vi.mocked(authApi.listInvites).mockResolvedValue([]);
  vi.mocked(adminApi.getKillSwitch).mockResolvedValue({ auto_responder_enabled: true });
  vi.mocked(adminApi.setKillSwitch).mockResolvedValue({ auto_responder_enabled: false });
  vi.mocked(adminApi.autorespondRuns).mockResolvedValue([]);
  vi.mocked(usersApi.auditLog).mockResolvedValue([]);
});

afterEach(() => vi.clearAllMocks());

describe("TeamPage", () => {
  it("lists members with roles and the correct action per role", async () => {
    render(<TeamPage />);
    expect(await screen.findByText("Eduardo")).toBeInTheDocument();
    // a member can be promoted; an admin can be demoted
    expect(screen.getByRole("button", { name: "Tornar admin" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rebaixar" })).toBeInTheDocument();
  });

  it("promotes a member to admin", async () => {
    render(<TeamPage />);
    await screen.findByText("Eduardo");
    await userEvent.click(screen.getByRole("button", { name: "Tornar admin" }));
    expect(usersApi.setRole).toHaveBeenCalledWith(2, "admin");
  });

  it("derives the invite state from the dates", async () => {
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

  it("engaging the kill switch needs 3 confirmations + the word, then toggles + updates the store", async () => {
    render(<TeamPage />);
    // wait for the current state to load (button only renders once enabled === true)
    const trigger = await screen.findByRole("button", {
      name: "Pausar TODAS as respostas automáticas",
    });
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole("button", { name: "Entendo o risco" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirmar de novo" }));
    await userEvent.type(screen.getByPlaceholderText("pausar-tudo"), "pausar-tudo");
    await userEvent.click(screen.getByRole("button", { name: "Aplicar" }));

    expect(adminApi.setKillSwitch).toHaveBeenCalledWith(false);
    // the store is updated for an immediate banner, even off the chat route
    expect(useKillSwitchStore.getState().autoResponderEnabled).toBe(false);
  });

  it("re-enabling auto-respond is a single safe click", async () => {
    vi.mocked(adminApi.getKillSwitch).mockResolvedValue({ auto_responder_enabled: false });
    vi.mocked(adminApi.setKillSwitch).mockResolvedValue({ auto_responder_enabled: true });
    render(<TeamPage />);
    const btn = await screen.findByRole("button", { name: "Reativar respostas automáticas" });
    await userEvent.click(btn);
    expect(adminApi.setKillSwitch).toHaveBeenCalledWith(true);
  });

  it("shows the admin oversight sections (global runs + audit log)", async () => {
    render(<TeamPage />);
    expect(await screen.findByText("Atividade automática (todos)")).toBeInTheDocument();
    expect(screen.getByText("Log de auditoria")).toBeInTheDocument();
    expect(adminApi.autorespondRuns).toHaveBeenCalled();
    expect(usersApi.auditLog).toHaveBeenCalled();
  });

  it("hides everything from non-admins", () => {
    useAuthStore.setState({ user: MEMBER });
    render(<TeamPage />);
    expect(screen.getByText(/não tem permissão/)).toBeInTheDocument();
    expect(screen.queryByText("Membros da equipe")).not.toBeInTheDocument();
  });
});
