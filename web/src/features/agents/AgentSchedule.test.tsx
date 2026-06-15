import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { agentsApi } from "../../lib/api/agents";
import type { Agent, AutoSchedule } from "../../lib/api/types";
import { AgentSchedule } from "./AgentSchedule";

vi.mock("../../lib/api/agents", () => ({ agentsApi: { updateSettings: vi.fn() } }));

const onChanged = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(agentsApi.updateSettings).mockResolvedValue({} as Agent);
});
afterEach(() => vi.clearAllMocks());

describe("AgentSchedule", () => {
  it("enabling + saving sends a single auto_schedule window", async () => {
    render(<AgentSchedule slug="backend-julio" schedule={null} onChanged={onChanged} />);
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Salvar horário" }));
    expect(agentsApi.updateSettings).toHaveBeenCalledWith("backend-julio", {
      auto_schedule: {
        tz: expect.any(String),
        windows: [{ days: [1, 2, 3, 4, 5], start: "09:00", end: "18:00" }],
      },
    });
  });

  it("turning it off clears the schedule (always-on)", async () => {
    const sched: AutoSchedule = {
      tz: "America/Sao_Paulo",
      windows: [{ days: [1, 2, 3], start: "08:00", end: "12:00" }],
    };
    render(<AgentSchedule slug="backend-julio" schedule={sched} onChanged={onChanged} />);
    await userEvent.click(screen.getByRole("checkbox")); // was enabled → disable
    await userEvent.click(screen.getByRole("button", { name: "Salvar horário" }));
    expect(agentsApi.updateSettings).toHaveBeenCalledWith("backend-julio", {
      clear_auto_schedule: true,
    });
  });

  it("rejects an empty day selection client-side", async () => {
    render(<AgentSchedule slug="backend-julio" schedule={null} onChanged={onChanged} />);
    await userEvent.click(screen.getByRole("checkbox")); // enable (defaults Seg..Sex)
    for (const label of ["Seg", "Ter", "Qua", "Qui", "Sex"]) {
      await userEvent.click(screen.getByRole("button", { name: label }));
    }
    await userEvent.click(screen.getByRole("button", { name: "Salvar horário" }));
    expect(agentsApi.updateSettings).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/ao menos um dia/);
  });
});
