import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { agentsApi } from "../../lib/api/agents";
import { presetsApi } from "../../lib/api/presets";
import type { Agent, Preset } from "../../lib/api/types";
import { AgentPresets } from "./AgentPresets";

vi.mock("../../lib/api/agents", () => ({ agentsApi: { applyPreset: vi.fn() } }));
vi.mock("../../lib/api/presets", () => ({
  presetsApi: { list: vi.fn(), create: vi.fn(), remove: vi.fn() },
}));

const AGENT = {
  slug: "backend-julio",
  mode: "inbox",
  max_auto_per_hour: 10,
  auto_timeout_secs: 120,
  allow_write: false,
  block_hidden_files: true,
  block_sensitive_paths: true,
  confine_to_dir: true,
  denied_paths: [],
  trusted_senders: [],
  require_approval: false,
  auto_paused: false,
  max_auto_tokens_per_day: null,
  max_auto_cost_usd_per_day: null,
} as unknown as Agent;

const SAFE: Preset = {
  id: 1,
  owner_id: null,
  name: "Estrito (padrão)",
  settings: { ...AGENT } as unknown as Preset["settings"],
  created_at: "2026-06-13T10:00:00Z",
};

const onChanged = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(presetsApi.list).mockResolvedValue([SAFE]);
  vi.mocked(agentsApi.applyPreset).mockResolvedValue(AGENT);
  vi.mocked(presetsApi.create).mockResolvedValue(SAFE);
});
afterEach(() => vi.clearAllMocks());

async function open() {
  render(<AgentPresets agent={AGENT} onChanged={onChanged} />);
  await userEvent.click(screen.getByRole("button", { name: /Presets de guardrails/ }));
}

describe("AgentPresets", () => {
  it("lists presets on open", async () => {
    await open();
    expect(await screen.findByText("Estrito (padrão)")).toBeInTheDocument();
    expect(presetsApi.list).toHaveBeenCalled();
  });

  it("applies a safe preset directly (no danger gate)", async () => {
    await open();
    await userEvent.click(await screen.findByRole("button", { name: "Aplicar" }));
    expect(agentsApi.applyPreset).toHaveBeenCalledWith("backend-julio", 1);
    expect(onChanged).toHaveBeenCalled();
  });

  it("saves the current config as a new preset", async () => {
    await open();
    await userEvent.type(screen.getByLabelText("Nome do preset"), "Meu preset");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(presetsApi.create).toHaveBeenCalledWith(
      "Meu preset",
      expect.objectContaining({ mode: "inbox" }),
    );
  });
});
