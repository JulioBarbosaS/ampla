import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { messagesApi } from "../../lib/api/messages";
import { useChatStore } from "../../stores/chat";
import { BroadcastPanel } from "./BroadcastPanel";

vi.mock("../../lib/api/messages", () => ({
  messagesApi: { broadcast: vi.fn() },
}));

beforeEach(() => {
  useChatStore.setState({
    perspective: "backend-julio",
    partner: "@frontend-team",
    directory: [
      { slug: "mobile-eduardo", display_name: "Mobile", online: true },
      { slug: "infra-maria", display_name: "Infra", online: false },
    ],
    groups: [
      {
        slug: "frontend-team",
        display_name: "Time Frontend",
        created_by: 1,
        created_at: "",
        members: ["mobile-eduardo", "infra-maria"],
      },
    ],
    online: { "mobile-eduardo": true, "infra-maria": false },
    conversations: {},
  });
});

afterEach(() => vi.clearAllMocks());

describe("BroadcastPanel", () => {
  it("lists the members of the selected group", () => {
    render(<BroadcastPanel perspective="backend-julio" target="@frontend-team" />);
    expect(screen.getByText("mobile-eduardo")).toBeInTheDocument();
    expect(screen.getByText("infra-maria")).toBeInTheDocument();
    expect(screen.getByText(/Destinatários \(2\)/)).toBeInTheDocument();
  });

  it("@all broadcasts to every agent in the directory", () => {
    render(<BroadcastPanel perspective="backend-julio" target="@all" />);
    expect(screen.getByText(/Destinatários \(2\)/)).toBeInTheDocument();
  });

  it("broadcasts and shows the humanized fan-out result", async () => {
    vi.mocked(messagesApi.broadcast).mockResolvedValue({
      group: "@frontend-team",
      sent: ["mobile-eduardo"],
      skipped: ["infra-maria"],
      message_ids: [101],
    });
    render(<BroadcastPanel perspective="backend-julio" target="@frontend-team" />);
    await userEvent.type(screen.getByPlaceholderText(/Transmitir para/), "deploy às 18h");
    await userEvent.click(screen.getByRole("button", { name: "Transmitir" }));

    expect(messagesApi.broadcast).toHaveBeenCalledWith(
      "backend-julio",
      "@frontend-team",
      "deploy às 18h",
      { type: "notification", priority: "normal" },
    );
    expect(await screen.findByText(/1 enviado/)).toBeInTheDocument();
    // infra-maria appears as "skipped" in the result (unique text in the result block)
    expect(screen.getByText(/não recebe\(m\): infra-maria/)).toBeInTheDocument();
  });
});
