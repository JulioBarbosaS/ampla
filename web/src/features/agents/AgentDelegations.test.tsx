import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { agentsApi } from "../../lib/api/agents";
import type { Delegation } from "../../lib/api/types";
import { AgentDelegations } from "./AgentDelegations";

vi.mock("../../lib/api/agents", () => ({ agentsApi: { delegations: vi.fn() } }));

function deleg(overrides: Partial<Delegation> = {}): Delegation {
  return {
    id: 1,
    from_agent: "backend-julio",
    to_agent: "mobile-eduardo",
    task: "Revisar o login",
    root_message_id: 10,
    result_message_id: null,
    status: "open",
    created_at: "2026-06-15T10:00:00Z",
    updated_at: "2026-06-15T10:00:00Z",
    ...overrides,
  };
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.clearAllMocks());

describe("AgentDelegations", () => {
  it("lazy-loads on open and shows outgoing direction + status", async () => {
    vi.mocked(agentsApi.delegations).mockResolvedValue([deleg()]);
    render(<AgentDelegations slug="backend-julio" />);
    expect(agentsApi.delegations).not.toHaveBeenCalled(); // lazy

    await userEvent.click(screen.getByRole("button", { name: /Delegações/ }));
    expect(await screen.findByText("Revisar o login")).toBeInTheDocument();
    expect(screen.getByText("aberta")).toBeInTheDocument();
    expect(screen.getByText("para")).toBeInTheDocument(); // backend-julio delegated out
    expect(agentsApi.delegations).toHaveBeenCalledWith("backend-julio");
  });

  it("shows incoming direction when the agent is the delegate", async () => {
    vi.mocked(agentsApi.delegations).mockResolvedValue([
      deleg({ from_agent: "infra-maria", to_agent: "backend-julio", status: "completed" }),
    ]);
    render(<AgentDelegations slug="backend-julio" />);
    await userEvent.click(screen.getByRole("button", { name: /Delegações/ }));
    expect(await screen.findByText("de")).toBeInTheDocument();
    expect(screen.getByText("concluída")).toBeInTheDocument();
  });

  it("shows an empty state when there are none", async () => {
    vi.mocked(agentsApi.delegations).mockResolvedValue([]);
    render(<AgentDelegations slug="backend-julio" />);
    await userEvent.click(screen.getByRole("button", { name: /Delegações/ }));
    expect(await screen.findByText("Nenhuma delegação ainda.")).toBeInTheDocument();
  });
});
