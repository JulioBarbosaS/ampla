import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { adminApi } from "../../lib/api/admin";
import type { InstanceMetrics as Metrics } from "../../lib/api/types";
import { InstanceMetrics } from "./InstanceMetrics";

vi.mock("../../lib/api/admin", () => ({ adminApi: { metrics: vi.fn() } }));

const SNAP: Metrics = {
  window_days: 7,
  generated_at: "2026-06-26T12:00:00Z",
  messages_total: 42,
  autorespond: {
    total_runs: 5,
    by_result: { replied: 3, blocked: 2 },
    timed_out: 1,
    total_cost_usd: 0.1234,
    total_output_tokens: 500,
    total_input_tokens: 1000,
    avg_duration_ms: 2400,
  },
  autorespond_daily: [
    { date: "2026-06-25", runs: 2, cost_usd: 0.05 },
    { date: "2026-06-26", runs: 3, cost_usd: 0.0734 },
  ],
  audit_events: [
    { event: "agent_created", count: 4 },
    { event: "kill_switch_toggled", count: 1 },
  ],
};

beforeEach(() => vi.mocked(adminApi.metrics).mockResolvedValue(SNAP));
afterEach(() => vi.clearAllMocks());

describe("InstanceMetrics", () => {
  it("loads the 7-day snapshot and renders the headline stats", async () => {
    render(<InstanceMetrics />);
    expect(await screen.findByText("42")).toBeInTheDocument(); // messages
    expect(screen.getByText("5")).toBeInTheDocument(); // runs
    expect(screen.getByText("$0.12")).toBeInTheDocument(); // cost (2 decimals)
    expect(screen.getByText(/replied/)).toBeInTheDocument();
    expect(screen.getByText(/blocked/)).toBeInTheDocument();
    expect(screen.getByText(/agent_created/)).toBeInTheDocument();
    expect(adminApi.metrics).toHaveBeenCalledWith(7);
  });

  it("refetches when the time window changes", async () => {
    render(<InstanceMetrics />);
    await screen.findByText("42");
    await userEvent.selectOptions(screen.getByLabelText("Janela de tempo"), "30");
    await waitFor(() => expect(adminApi.metrics).toHaveBeenCalledWith(30));
  });
});
