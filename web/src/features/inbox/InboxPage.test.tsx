import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AppNotification } from "../../lib/api/types";
import { useInboxStore } from "../../stores/inbox";
import { InboxPage } from "./InboxPage";

const navigate = vi.fn();
vi.mock("react-router-dom", async (orig) => ({
  ...(await orig<typeof import("react-router-dom")>()),
  useNavigate: () => navigate,
}));

vi.mock("../../lib/api/notifications", () => ({
  notificationsApi: {
    list: vi.fn(),
    unreadCount: vi.fn(),
    triage: vi.fn(),
    readAll: vi.fn(),
    getPrefs: vi.fn(),
    setPrefs: vi.fn(),
  },
}));

import { notificationsApi } from "../../lib/api/notifications";

function notif(over: Partial<AppNotification> = {}): AppNotification {
  return {
    id: 1,
    subject_type: "dm",
    subject_key: "dm:backend-julio:mobile-eduardo",
    agent_slug: "backend-julio",
    reason: "direct_message",
    title: "mobile-eduardo enviou uma mensagem para backend-julio",
    link: "/?perspective=backend-julio&partner=mobile-eduardo&msg=1",
    actor: "mobile-eduardo",
    unread: true,
    status: "inbox",
    created_at: "2026-06-11T12:00:00Z",
    updated_at: "2026-06-11T12:00:00Z",
    last_read_at: null,
    ...over,
  };
}

beforeEach(() => {
  navigate.mockClear();
  useInboxStore.setState({ items: [], unreadCount: 0 });
  vi.mocked(notificationsApi.list).mockResolvedValue([notif()]);
  vi.mocked(notificationsApi.unreadCount).mockResolvedValue({ unread_count: 1 });
  vi.mocked(notificationsApi.triage).mockResolvedValue(notif({ unread: false }));
  vi.mocked(notificationsApi.readAll).mockResolvedValue({ unread_count: 0 });
  vi.mocked(notificationsApi.getPrefs).mockResolvedValue({ notify_level: "mentions_and_direct" });
  vi.mocked(notificationsApi.setPrefs).mockResolvedValue({ notify_level: "mute" });
});

afterEach(() => vi.clearAllMocks());

function renderInbox() {
  render(
    <MemoryRouter>
      <InboxPage />
    </MemoryRouter>,
  );
}

describe("InboxPage", () => {
  it("loads the inbox view and renders a notification row", async () => {
    renderInbox();
    expect(await screen.findByText(/enviou uma mensagem/)).toBeInTheDocument();
    expect(screen.getByText("mensagem")).toBeInTheDocument(); // dm reason chip
    expect(notificationsApi.list).toHaveBeenCalledWith({ status: "inbox" });
  });

  it("switches to the Saved view", async () => {
    renderInbox();
    await screen.findByText(/enviou uma mensagem/);
    await userEvent.click(screen.getByRole("button", { name: "Salvos" }));
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalledWith({ status: "saved" }));
  });

  it("filters by the @Menções canned view (reason filter)", async () => {
    renderInbox();
    await screen.findByText(/enviou uma mensagem/);
    await userEvent.click(screen.getByRole("button", { name: "Menções" }));
    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalledWith({ reason: "mention" }));
  });

  it("triages 'Concluir' through the API and reloads", async () => {
    renderInbox();
    const row = (await screen.findByText(/enviou uma mensagem/)).closest("li") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "Concluir" }));
    expect(notificationsApi.triage).toHaveBeenCalledWith(1, { status: "done" });
  });

  it("opening a notification navigates to its deep link", async () => {
    renderInbox();
    await userEvent.click(await screen.findByText(/enviou uma mensagem/));
    expect(navigate).toHaveBeenCalledWith(
      "/?perspective=backend-julio&partner=mobile-eduardo&msg=1",
    );
  });

  it("'Marcar todas como lidas' calls read-all and reloads", async () => {
    renderInbox();
    await screen.findByText(/enviou uma mensagem/);
    await userEvent.click(screen.getByRole("button", { name: "Marcar todas como lidas" }));
    expect(notificationsApi.readAll).toHaveBeenCalled();
  });

  it("loads the delivery level and changes it via prefs", async () => {
    renderInbox();
    await screen.findByText(/enviou uma mensagem/);
    const select = screen.getByLabelText("Nível de notificação") as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe("mentions_and_direct"));
    await userEvent.selectOptions(select, "mute");
    expect(notificationsApi.setPrefs).toHaveBeenCalledWith("mute");
  });

  it("shows the inbox-zero empty state", async () => {
    vi.mocked(notificationsApi.list).mockResolvedValue([]);
    vi.mocked(notificationsApi.unreadCount).mockResolvedValue({ unread_count: 0 });
    renderInbox();
    expect(await screen.findByText(/inbox-zero/)).toBeInTheDocument();
  });
});
