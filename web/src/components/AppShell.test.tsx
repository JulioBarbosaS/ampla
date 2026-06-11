import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useAuthStore } from "../stores/auth";
import { useKillSwitchStore } from "../stores/killSwitch";
import { AppShell } from "./AppShell";

function renderShell() {
  render(
    <MemoryRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<div>conteúdo</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  useAuthStore.setState({
    user: { id: 1, email: "j@example.com", name: "Julio", role: "admin", created_at: "" },
  });
  useKillSwitchStore.setState({ autoResponderEnabled: true });
});

afterEach(() => {
  useAuthStore.setState({ user: null });
  useKillSwitchStore.setState({ autoResponderEnabled: true });
});

describe("AppShell kill-switch banner", () => {
  it("shows no banner while auto-respond is enabled", () => {
    renderShell();
    expect(screen.queryByText(/suspensas pelo administrador/)).not.toBeInTheDocument();
  });

  it("shows the global banner when the kill switch is engaged", () => {
    useKillSwitchStore.setState({ autoResponderEnabled: false });
    renderShell();
    expect(screen.getByRole("alert")).toHaveTextContent(/suspensas pelo administrador/);
  });
});
