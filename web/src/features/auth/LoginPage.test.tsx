import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../../stores/auth";
import { LoginPage } from "./LoginPage";

vi.mock("../../lib/api/auth", () => ({ authApi: { login: vi.fn() } }));

import { authApi } from "../../lib/api/auth";

function renderLogin() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(authApi.login).mockReset();
  useAuthStore.setState({ user: null });
});

describe("LoginPage", () => {
  it("renders the welcome header, fields and the social/forgot footer", () => {
    renderLogin();
    expect(screen.getByRole("heading", { name: "Bem-vindo de volta" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("placeholder", "voce@exemplo.com");
    expect(screen.getByLabelText("Senha")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Entrar" })).toBeEnabled();

    // social sign-in + password recovery are present but not wired yet
    expect(screen.getByRole("button", { name: /Google/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /GitHub/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Esqueci minha senha" })).toBeDisabled();
    expect(screen.getByRole("link", { name: "Criar conta" })).toHaveAttribute("href", "/register");
  });

  it("submits credentials and stores the returned user", async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      token: "t",
      user: { id: 1, email: "a@b.c", name: "A", role: "member", created_at: "" },
    });
    renderLogin();
    await userEvent.type(screen.getByLabelText("Email"), "a@b.c");
    await userEvent.type(screen.getByLabelText("Senha"), "secret");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));

    expect(authApi.login).toHaveBeenCalledWith({ email: "a@b.c", password: "secret" });
    expect(useAuthStore.getState().user?.email).toBe("a@b.c");
  });
});
