import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { adminApi } from "../../lib/api/admin";
import type { AutorespondRun } from "../../lib/api/types";
import { AdminAutorespondRuns } from "./AdminAutorespondRuns";

vi.mock("../../lib/api/admin", () => ({ adminApi: { autorespondRuns: vi.fn() } }));

const RUN: AutorespondRun = {
  id: 1,
  agent_slug: "backend-ana",
  trigger_message_id: 10,
  from_sender: "mobile-edu",
  result: "replied",
  reason: null,
  reply_preview: "feito",
  tools_allowed: "read",
  tools_disallowed: "",
  guardrails: { sandbox: "docker", allow_write: false },
  duration_ms: 1200,
  timed_out: false,
  input_tokens: 100,
  output_tokens: 50,
  cost_usd: 0.0012,
  created_at: "2026-06-23T10:00:00Z",
};

beforeEach(() => vi.mocked(adminApi.autorespondRuns).mockResolvedValue([RUN]));
afterEach(() => vi.clearAllMocks());

describe("AdminAutorespondRuns", () => {
  it("loads the instance-wide runs and shows which agent ran", async () => {
    render(<AdminAutorespondRuns />);
    expect(await screen.findByText("backend-ana")).toBeInTheDocument();
    expect(screen.getByText("respondeu")).toBeInTheDocument();
    expect(adminApi.autorespondRuns).toHaveBeenCalled();
  });

  it("shows an empty state when there are no runs", async () => {
    vi.mocked(adminApi.autorespondRuns).mockResolvedValue([]);
    render(<AdminAutorespondRuns />);
    expect(await screen.findByText(/Nenhuma resposta automática/)).toBeInTheDocument();
  });
});
