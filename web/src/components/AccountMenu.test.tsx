import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../stores/auth";
import { useThemeStore } from "../stores/theme";
import { AccountMenu } from "./AccountMenu";

const navigate = vi.fn();
vi.mock("react-router-dom", async (orig) => ({
  ...(await orig<typeof import("react-router-dom")>()),
  useNavigate: () => navigate,
}));

vi.mock("../lib/api/auth", () => ({
  authApi: { logout: vi.fn().mockResolvedValue(null) },
}));

import { authApi } from "../lib/api/auth";

beforeEach(() => {
  navigate.mockClear();
  vi.mocked(authApi.logout).mockClear();
  useThemeStore.getState().setTheme("dark");
  useAuthStore.setState({
    user: { id: 1, email: "julio@example.com", name: "Julio", role: "admin", created_at: "" },
  });
});

afterEach(() => {
  useAuthStore.setState({ user: null });
});

describe("AccountMenu", () => {
  it("opens the drawer with the account options", async () => {
    render(<AccountMenu />);
    expect(screen.queryByRole("menu")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Conta e configurações" }));

    expect(screen.getByRole("menu")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Perfil" })).toBeInTheDocument();
    expect(screen.getByText("Tema")).toBeInTheDocument();
    expect(screen.getByText("Idioma")).toBeInTheDocument();
    expect(screen.getByText("em breve")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Sair" })).toBeInTheDocument();
  });

  it("navigates to the profile page", async () => {
    render(<AccountMenu />);
    await userEvent.click(screen.getByRole("button", { name: "Conta e configurações" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Perfil" }));
    expect(navigate).toHaveBeenCalledWith("/settings");
  });

  it("switches and persists the theme", async () => {
    render(<AccountMenu />);
    await userEvent.click(screen.getByRole("button", { name: "Conta e configurações" }));
    await userEvent.click(screen.getByRole("button", { name: "Claro" }));
    expect(useThemeStore.getState().theme).toBe("light");
  });

  it("logs out: expires the cookie and clears the user", async () => {
    render(<AccountMenu />);
    await userEvent.click(screen.getByRole("button", { name: "Conta e configurações" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Sair" }));
    expect(authApi.logout).toHaveBeenCalledOnce();
    expect(useAuthStore.getState().user).toBeNull();
  });
});
