import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    subscribe: vi.fn(),
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
  vi.mocked(notificationsApi.subscribe).mockResolvedValue({
    subject_key: "dm:backend-julio:mobile-eduardo",
    state: "ignored",
  });
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

  it("labels a previously-unlabeled reason in pt-BR (no raw English chip)", async () => {
    vi.mocked(notificationsApi.list).mockResolvedValue([
      notif({ reason: "escalation", title: "agente escalou para você" }),
    ]);
    renderInbox();
    expect(await screen.findByText("agente escalou para você")).toBeInTheDocument();
    expect(screen.getByText("escalação")).toBeInTheDocument(); // not the raw "escalation"
    expect(screen.queryByText("escalation")).not.toBeInTheDocument();
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

  it("submits the search box as a q qualifier", async () => {
    renderInbox();
    await screen.findByText(/enviou uma mensagem/);
    await userEvent.type(screen.getByLabelText("Buscar no inbox"), "is:done from:bob");
    await userEvent.click(screen.getByRole("button", { name: "Buscar" }));
    await waitFor(() =>
      expect(notificationsApi.list).toHaveBeenCalledWith(
        expect.objectContaining({ q: "is:done from:bob" }),
      ),
    );
  });

  it("triages 'Concluir' through the API and reloads", async () => {
    renderInbox();
    const row = (await screen.findByText(/enviou uma mensagem/)).closest("li") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "Concluir" }));
    expect(notificationsApi.triage).toHaveBeenCalledWith(1, { status: "done" });
  });

  it("'Ignorar' mutes the thread and archives the row", async () => {
    renderInbox();
    const row = (await screen.findByText(/enviou uma mensagem/)).closest("li") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "Ignorar" }));
    expect(notificationsApi.subscribe).toHaveBeenCalledWith(
      "dm:backend-julio:mobile-eduardo",
      "ignored",
    );
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

  it("bulk-concludes the selected rows", async () => {
    vi.mocked(notificationsApi.list).mockResolvedValue([
      notif({ id: 1 }),
      notif({ id: 2, title: "segundo aviso", subject_key: "dm:a:b" }),
    ]);
    renderInbox();
    await screen.findByText(/segundo aviso/);
    const checks = screen.getAllByRole("checkbox");
    await userEvent.click(checks[0]);
    await userEvent.click(checks[1]);
    await userEvent.click(screen.getByRole("button", { name: "Concluir selecionadas" }));
    expect(notificationsApi.triage).toHaveBeenCalledWith(1, { status: "done" });
    expect(notificationsApi.triage).toHaveBeenCalledWith(2, { status: "done" });
  });

  it("keyboard 'e' concludes the current selection", async () => {
    renderInbox();
    await screen.findByText(/enviou uma mensagem/);
    await userEvent.click(screen.getByRole("checkbox", { name: /Selecionar/ }));
    fireEvent.keyDown(document, { key: "e" });
    await waitFor(() =>
      expect(notificationsApi.triage).toHaveBeenCalledWith(1, { status: "done" }),
    );
  });

  it("offers a desktop-notifications opt-in and requests permission on enable", async () => {
    const requestPermission = vi.fn().mockResolvedValue("granted");
    // The toggle flow only reads permission + requestPermission (never `new
    // Notification`), so a plain object stub suffices.
    vi.stubGlobal("Notification", { permission: "default", requestPermission });
    localStorage.clear();
    renderInbox();
    await screen.findByText(/enviou uma mensagem/);
    const toggle = screen.getByLabelText("Notificações no desktop") as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    await userEvent.click(toggle);
    expect(requestPermission).toHaveBeenCalled();
    await waitFor(() => expect(toggle.checked).toBe(true));
    // Restore "unsupported" so the toggle is hidden for the other tests (and its
    // checkbox doesn't shift indices in the bulk-selection test).
    vi.stubGlobal("Notification", undefined);
  });

  it("shows the inbox-zero empty state", async () => {
    vi.mocked(notificationsApi.list).mockResolvedValue([]);
    vi.mocked(notificationsApi.unreadCount).mockResolvedValue({ unread_count: 0 });
    renderInbox();
    expect(await screen.findByText(/inbox-zero/)).toBeInTheDocument();
  });
});
