import { render, screen, within } from "@testing-library/react";
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

async function openDrawer() {
  await userEvent.click(screen.getByRole("button", { name: "Conta e configurações" }));
}

describe("AccountMenu", () => {
  it("opens the drawer with the account options, theme collapsed", async () => {
    render(<AccountMenu />);
    expect(screen.queryByRole("menu")).toBeNull();

    await openDrawer();

    const menu = screen.getByRole("menu");
    // header shows the account name and email (next to the avatar)
    expect(within(menu).getByText("Julio")).toBeInTheDocument();
    expect(within(menu).getByText("julio@example.com")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Perfil" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tema" })).toBeInTheDocument();
    expect(screen.getByText("Idioma")).toBeInTheDocument();
    expect(screen.getByText("em breve")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Sair" })).toBeInTheDocument();

    // theme options stay hidden until the user expands "Tema"
    expect(screen.queryByRole("button", { name: "Claro" })).toBeNull();
  });

  it("navigates to the profile page", async () => {
    render(<AccountMenu />);
    await openDrawer();
    await userEvent.click(screen.getByRole("menuitem", { name: "Perfil" }));
    expect(navigate).toHaveBeenCalledWith("/settings");
  });

  it("expands the theme submenu and switches/persists the choice", async () => {
    render(<AccountMenu />);
    await openDrawer();
    await userEvent.click(screen.getByRole("button", { name: "Tema" }));

    // all three options appear
    for (const label of ["Claro", "Escuro", "Tema do dispositivo"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }

    await userEvent.click(screen.getByRole("button", { name: "Claro" }));
    expect(useThemeStore.getState().preference).toBe("light");

    await userEvent.click(screen.getByRole("button", { name: "Tema do dispositivo" }));
    expect(useThemeStore.getState().preference).toBe("system");
  });

  it("logs out: expires the cookie and clears the user", async () => {
    render(<AccountMenu />);
    await openDrawer();
    await userEvent.click(screen.getByRole("menuitem", { name: "Sair" }));
    expect(authApi.logout).toHaveBeenCalledOnce();
    expect(useAuthStore.getState().user).toBeNull();
  });
});
