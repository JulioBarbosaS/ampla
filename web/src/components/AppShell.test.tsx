import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../stores/auth";
import { useInboxStore } from "../stores/inbox";
import { useKillSwitchStore } from "../stores/killSwitch";
import { AppShell } from "./AppShell";

vi.mock("../lib/api/notifications", () => ({
  notificationsApi: { unreadCount: vi.fn().mockResolvedValue({ unread_count: 0 }) },
}));

import { notificationsApi } from "../lib/api/notifications";

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
  vi.mocked(notificationsApi.unreadCount).mockResolvedValue({ unread_count: 0 });
  useAuthStore.setState({
    user: { id: 1, email: "j@example.com", name: "Julio", role: "admin", created_at: "" },
  });
  useKillSwitchStore.setState({ autoResponderEnabled: true });
  useInboxStore.setState({ items: [], unreadCount: 0 });
});

afterEach(() => {
  useAuthStore.setState({ user: null });
  useKillSwitchStore.setState({ autoResponderEnabled: true });
  useInboxStore.setState({ items: [], unreadCount: 0 });
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

describe("AppShell inbox bell", () => {
  it("fetches and shows the unread badge", async () => {
    vi.mocked(notificationsApi.unreadCount).mockResolvedValue({ unread_count: 3 });
    renderShell();
    await waitFor(() => expect(useInboxStore.getState().unreadCount).toBe(3));
    expect(screen.getByLabelText(/Inbox \(3 não lidas\)/)).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("shows no badge at inbox-zero", async () => {
    renderShell();
    await waitFor(() => expect(notificationsApi.unreadCount).toHaveBeenCalled());
    expect(screen.getByLabelText("Inbox")).toBeInTheDocument(); // no count suffix
  });
});
