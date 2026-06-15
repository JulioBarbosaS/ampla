import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { agentsApi } from "../../lib/api/agents";
import { AgentEscalation } from "./AgentEscalation";

vi.mock("../../lib/api/agents", () => ({ agentsApi: { updateSettings: vi.fn() } }));

const onChanged = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(agentsApi.updateSettings).mockResolvedValue({} as never);
});
afterEach(() => vi.clearAllMocks());

describe("AgentEscalation", () => {
  it("saves the toggled selection in canonical order", async () => {
    render(<AgentEscalation slug="backend-julio" escalateOn={["failed"]} onChanged={onChanged} />);
    // add outside_hours (failed already selected) → canonical order keeps failed first
    await userEvent.click(screen.getByRole("button", { name: "Fora do horário" }));
    await userEvent.click(screen.getByRole("button", { name: "Salvar escalação" }));
    expect(agentsApi.updateSettings).toHaveBeenCalledWith("backend-julio", {
      escalate_on: ["failed", "outside_hours"],
    });
    expect(onChanged).toHaveBeenCalled();
  });

  it("can disable escalation entirely (empty list)", async () => {
    render(<AgentEscalation slug="backend-julio" escalateOn={["failed"]} onChanged={onChanged} />);
    await userEvent.click(screen.getByRole("button", { name: "Falhou" })); // deselect
    await userEvent.click(screen.getByRole("button", { name: "Salvar escalação" }));
    expect(agentsApi.updateSettings).toHaveBeenCalledWith("backend-julio", { escalate_on: [] });
  });

  it("reflects the initial selection via aria-pressed", () => {
    render(<AgentEscalation slug="backend-julio" escalateOn={["blocked"]} onChanged={onChanged} />);
    expect(screen.getByRole("button", { name: "Bloqueado (filtro)" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Falhou" })).toHaveAttribute("aria-pressed", "false");
  });
});
