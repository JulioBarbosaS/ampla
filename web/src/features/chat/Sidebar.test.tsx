import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
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

beforeEach(() => {
  useChatStore.setState({
    perspective: "backend-julio",
    partner: null,
    directory: [
      { slug: "backend-julio", display_name: "Backend", online: true },
      { slug: "mobile-eduardo", display_name: "Mobile do Eduardo", online: true },
      { slug: "infra-maria", display_name: "Infra da Maria", online: false },
    ],
    online: { "backend-julio": true, "mobile-eduardo": true, "infra-maria": false },
    conversations: {},
  });
});

describe("Sidebar", () => {
  it("lista a equipe sem o próprio agente, com presença", () => {
    render(<Sidebar />);
    expect(screen.getByText("mobile-eduardo")).toBeInTheDocument();
    expect(screen.getByText("infra-maria")).toBeInTheDocument();
    // o agente-perspectiva não aparece na lista da equipe
    expect(screen.queryByRole("button", { name: /backend-julio/ })).not.toBeInTheDocument();
    expect(screen.getAllByLabelText("online")).toHaveLength(1);
    expect(screen.getAllByLabelText("offline")).toHaveLength(1);
  });

  it("clicar num agente seleciona o parceiro da conversa", async () => {
    render(<Sidebar />);
    await userEvent.click(screen.getByText("mobile-eduardo"));
    expect(useChatStore.getState().partner).toBe("mobile-eduardo");
  });
});
