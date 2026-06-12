import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { agentsApi } from "../../lib/api/agents";
import type { Approval } from "../../lib/api/types";
import { AgentApprovals } from "./AgentApprovals";

vi.mock("../../lib/api/agents", () => ({
  agentsApi: { approvals: vi.fn(), decideApproval: vi.fn() },
}));

const APPROVAL: Approval = {
  id: 7,
  agent_slug: "backend-julio",
  trigger_message_id: 42,
  to_agent: "mobile-eduardo",
  draft_body: "Sim: POST /api/v1/auth/password-reset",
  status: "pending",
  decided_by: null,
  decided_at: null,
  created_at: "2026-06-12T10:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(agentsApi.decideApproval).mockResolvedValue({ ...APPROVAL, status: "approved" });
});
afterEach(() => vi.clearAllMocks());

async function openSection() {
  render(<AgentApprovals slug="backend-julio" />);
  await userEvent.click(screen.getByRole("button", { name: /Pendências de aprovação/ }));
}

describe("AgentApprovals", () => {
  it("is lazy: no fetch until the section is opened", () => {
    render(<AgentApprovals slug="backend-julio" />);
    expect(agentsApi.approvals).not.toHaveBeenCalled();
  });

  it("lists a pending approval with its draft on open", async () => {
    vi.mocked(agentsApi.approvals).mockResolvedValue([APPROVAL]);
    await openSection();
    expect(agentsApi.approvals).toHaveBeenCalledWith("backend-julio");
    expect(await screen.findByText(/password-reset/)).toBeInTheDocument();
    expect(screen.getByText("mobile-eduardo")).toBeInTheDocument();
  });

  it("approves through the API and drops the row", async () => {
    vi.mocked(agentsApi.approvals).mockResolvedValue([APPROVAL]);
    await openSection();
    await userEvent.click(await screen.findByRole("button", { name: "Aprovar" }));
    expect(agentsApi.decideApproval).toHaveBeenCalledWith(7, "approve", undefined);
    await waitFor(() => expect(screen.queryByText(/password-reset/)).not.toBeInTheDocument());
  });

  it("edits then sends the revised body", async () => {
    vi.mocked(agentsApi.approvals).mockResolvedValue([APPROVAL]);
    await openSection();
    await userEvent.click(await screen.findByRole("button", { name: "Editar e enviar" }));
    const textarea = screen.getByLabelText("Editar rascunho");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "resposta revisada");
    await userEvent.click(screen.getByRole("button", { name: "Enviar editado" }));
    expect(agentsApi.decideApproval).toHaveBeenCalledWith(7, "approve", "resposta revisada");
  });

  it("rejects through the API", async () => {
    vi.mocked(agentsApi.approvals).mockResolvedValue([APPROVAL]);
    await openSection();
    await userEvent.click(await screen.findByRole("button", { name: "Rejeitar" }));
    expect(agentsApi.decideApproval).toHaveBeenCalledWith(7, "reject", undefined);
  });

  it("shows an empty state when nothing is pending", async () => {
    vi.mocked(agentsApi.approvals).mockResolvedValue([]);
    await openSection();
    expect(await screen.findByText(/Nenhuma resposta aguardando/)).toBeInTheDocument();
  });
});
