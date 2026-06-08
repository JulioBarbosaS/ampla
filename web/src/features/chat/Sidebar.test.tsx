import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { groupsApi } from "../../lib/api/groups";
import { messagesApi } from "../../lib/api/messages";
import { useChatStore } from "../../stores/chat";
import { Sidebar } from "./Sidebar";

vi.mock("../../lib/api/agents", () => ({
  agentsApi: {
    mine: vi.fn().mockResolvedValue([
      {
        slug: "backend-julio",
        user_id: 1,
        display_name: "Backend",
        created_at: "",
        mode: "inbox",
        allowed_senders: null,
        max_auto_per_hour: 10,
        auto_timeout_secs: 120,
        instructions: "",
      },
    ]),
  },
}));

vi.mock("../../lib/api/groups", () => ({
  groupsApi: { list: vi.fn().mockResolvedValue([]) },
}));

vi.mock("../../lib/api/messages", () => ({
  messagesApi: { partners: vi.fn().mockResolvedValue([]) },
}));

beforeEach(() => {
  useChatStore.setState({
    perspective: "backend-julio",
    partner: null,
    directory: [
      { slug: "backend-julio", display_name: "Backend", online: true },
      { slug: "mobile-eduardo", display_name: "Mobile do Eduardo", online: true },
      { slug: "infra-maria", display_name: "Infra da Maria", online: false },
    ],
    groups: [],
    online: { "backend-julio": true, "mobile-eduardo": true, "infra-maria": false },
    conversations: {},
  });
});

describe("Sidebar", () => {
  it("lists the team without the user's own agent, with presence", () => {
    render(<Sidebar />);
    expect(screen.getByText("mobile-eduardo")).toBeInTheDocument();
    expect(screen.getByText("infra-maria")).toBeInTheDocument();
    // the perspective agent does not appear in the team list
    expect(screen.queryByRole("button", { name: /backend-julio/ })).not.toBeInTheDocument();
    expect(screen.getAllByLabelText("online")).toHaveLength(1);
    expect(screen.getAllByLabelText("offline")).toHaveLength(1);
  });

  it("clicking an agent selects the conversation partner", async () => {
    render(<Sidebar />);
    await userEvent.click(screen.getByText("mobile-eduardo"));
    expect(useChatStore.getState().partner).toBe("mobile-eduardo");
  });

  it("shows @all and the groups; clicking enters broadcast mode", async () => {
    // groups arrive via the API (the Sidebar loads and populates the store)
    vi.mocked(groupsApi.list).mockResolvedValueOnce([
      {
        slug: "frontend-team",
        display_name: "Time Frontend",
        created_by: 1,
        created_at: "",
        members: ["mobile-eduardo", "infra-maria"],
      },
    ]);
    render(<Sidebar />);
    expect(screen.getByText("@all")).toBeInTheDocument();
    const groupItem = await screen.findByText("@frontend-team");
    expect(screen.getByText(/2 membro\(s\)/)).toBeInTheDocument();

    await userEvent.click(groupItem);
    expect(useChatStore.getState().partner).toBe("@frontend-team");
  });

  it("shows the partner's last-message preview (without the [auto] prefix)", async () => {
    vi.mocked(messagesApi.partners).mockResolvedValueOnce([
      {
        agent: "mobile-eduardo",
        last_message: {
          id: 9,
          from: "mobile-eduardo",
          to: "backend-julio",
          body: "[auto] tudo certo com o deploy",
          created_at: "2026-06-06T10:00:00Z",
          type: "response",
          priority: "normal",
          group: null,
          thread_id: 9,
          in_reply_to: null,
          delivered_at: null,
          expires_at: null,
        },
      },
    ]);
    render(<Sidebar />);
    expect(await screen.findByText("tudo certo com o deploy")).toBeInTheDocument();
  });
});
