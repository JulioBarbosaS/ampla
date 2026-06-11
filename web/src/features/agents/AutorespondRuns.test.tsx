import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { agentsApi } from "../../lib/api/agents";
import type { AutorespondRun } from "../../lib/api/types";
import { AutorespondRuns } from "./AutorespondRuns";

vi.mock("../../lib/api/agents", () => ({
  agentsApi: { autorespondRuns: vi.fn() },
}));

const RUN: AutorespondRun = {
  id: 1,
  agent_slug: "backend-julio",
  trigger_message_id: 42,
  from_sender: "mobile-eduardo",
  result: "replied",
  reason: null,
  reply_preview: "Sim: POST /api/v1/auth/password-reset",
  tools_allowed: "Read,Grep,Glob",
  tools_disallowed: "Bash,Edit,Write",
  guardrails: { allow_write: false, block_sensitive_paths: true, sandbox: "host" },
  duration_ms: 1234,
  timed_out: false,
  input_tokens: null,
  output_tokens: null,
  cost_usd: null,
  created_at: "2026-06-11T10:00:00Z",
};

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.clearAllMocks());

describe("AutorespondRuns", () => {
  it("does not fetch until the section is opened (lazy)", () => {
    render(<AutorespondRuns slug="backend-julio" />);
    expect(agentsApi.autorespondRuns).not.toHaveBeenCalled();
  });

  it("loads and renders a run with its result and guardrail snapshot on open", async () => {
    vi.mocked(agentsApi.autorespondRuns).mockResolvedValue([RUN]);
    render(<AutorespondRuns slug="backend-julio" />);
    await userEvent.click(screen.getByRole("button", { name: /Atividade automática/ }));

    expect(agentsApi.autorespondRuns).toHaveBeenCalledWith("backend-julio");
    expect(await screen.findByText("respondeu")).toBeInTheDocument();
    expect(screen.getByText("mobile-eduardo")).toBeInTheDocument();
    expect(screen.getByText(/só leitura/)).toBeInTheDocument();
    expect(screen.getByText(/password-reset/)).toBeInTheDocument();
  });

  it("flags a trusted-sender run as full access", async () => {
    vi.mocked(agentsApi.autorespondRuns).mockResolvedValue([
      { ...RUN, guardrails: { ...RUN.guardrails, trusted_sender: true } },
    ]);
    render(<AutorespondRuns slug="backend-julio" />);
    await userEvent.click(screen.getByRole("button", { name: /Atividade automática/ }));
    expect(await screen.findByText(/remetente confiável/)).toBeInTheDocument();
  });

  it("shows an empty state when there are no runs", async () => {
    vi.mocked(agentsApi.autorespondRuns).mockResolvedValue([]);
    render(<AutorespondRuns slug="backend-julio" />);
    await userEvent.click(screen.getByRole("button", { name: /Atividade automática/ }));
    expect(await screen.findByText(/Nenhuma resposta automática/)).toBeInTheDocument();
  });
});
