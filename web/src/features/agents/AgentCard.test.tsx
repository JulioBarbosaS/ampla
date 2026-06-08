import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { agentsApi } from "../../lib/api/agents";
import { groupsApi } from "../../lib/api/groups";
import type { Agent, Group } from "../../lib/api/types";
import { AgentCard } from "./AgentCard";

vi.mock("../../lib/api/agents", () => ({
  agentsApi: {
    listKeys: vi.fn().mockResolvedValue([]),
    createKey: vi.fn(),
    revokeKey: vi.fn(),
    updateSettings: vi.fn(),
  },
}));

vi.mock("../../lib/api/groups", () => ({
  groupsApi: {
    addMember: vi.fn().mockResolvedValue(undefined),
    removeMember: vi.fn().mockResolvedValue(undefined),
  },
}));

const AGENT: Agent = {
  slug: "backend-julio",
  user_id: 1,
  display_name: "Backend",
  created_at: "",
  mode: "auto",
  allowed_senders: null,
  max_auto_per_hour: 10,
  auto_timeout_secs: 120,
  instructions: "",
};

const GROUPS: Group[] = [
  {
    slug: "frontend-team",
    display_name: "FE",
    created_by: 1,
    created_at: "",
    members: ["backend-julio"],
  },
  { slug: "infra-team", display_name: "Infra", created_by: 1, created_at: "", members: [] },
];

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.clearAllMocks());

describe("AgentCard", () => {
  it("shows presence status and the connection instructions", () => {
    render(<AgentCard agent={AGENT} online={true} groups={GROUPS} onChanged={() => {}} />);
    expect(screen.getByText("online")).toBeInTheDocument();
    expect(screen.getByText(/"agent_id": "backend-julio"/)).toBeInTheDocument();
  });

  it("reflects group membership (✓ member, + non-member)", () => {
    render(<AgentCard agent={AGENT} online={false} groups={GROUPS} onChanged={() => {}} />);
    expect(screen.getByRole("button", { name: /✓.*@frontend-team/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /\+.*@infra-team/ })).toBeInTheDocument();
  });

  it("joining and leaving a group calls the right API", async () => {
    const onGroupsChanged = vi.fn();
    render(
      <AgentCard
        agent={AGENT}
        online={false}
        groups={GROUPS}
        onChanged={() => {}}
        onGroupsChanged={onGroupsChanged}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /\+.*@infra-team/ }));
    expect(groupsApi.addMember).toHaveBeenCalledWith("infra-team", "backend-julio");

    await userEvent.click(screen.getByRole("button", { name: /✓.*@frontend-team/ }));
    expect(groupsApi.removeMember).toHaveBeenCalledWith("frontend-team", "backend-julio");
    expect(onGroupsChanged).toHaveBeenCalled();
  });

  it("lists the agent's keys on mount", () => {
    render(<AgentCard agent={AGENT} groups={[]} onChanged={() => {}} />);
    expect(agentsApi.listKeys).toHaveBeenCalledWith("backend-julio");
  });

  it("on key generation, shows the one-command 'amp connect' command", async () => {
    vi.mocked(agentsApi.createKey).mockResolvedValue({ id: 1, label: "", key: "amp_chave123" });
    render(<AgentCard agent={AGENT} groups={[]} onChanged={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "Gerar chave" }));
    const code = await screen.findByText(/amp connect /);
    expect(code.textContent).toMatch(/^amp connect [A-Za-z0-9_-]+$/); // base64url token
  });
});
