import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { schedulesApi } from "../../lib/api/schedules";
import type { ScheduledTask } from "../../lib/api/types";
import { AgentScheduledTasks } from "./AgentScheduledTasks";

vi.mock("../../lib/api/schedules", () => ({
  schedulesApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    runNow: vi.fn(),
  },
}));

function task(over: Partial<ScheduledTask> = {}): ScheduledTask {
  return {
    id: 1,
    owner_id: 1,
    agent_slug: "backend-julio",
    name: "Resumo diário",
    kind: "interval",
    spec: "3600",
    prompt: "resuma",
    tools: "read",
    enabled: true,
    next_run_at: "2026-06-23T13:00:00Z",
    last_run_at: null,
    last_status: null,
    created_by: "user:1",
    created_at: "",
    updated_at: "",
    ...over,
  };
}

beforeEach(() => {
  vi.mocked(schedulesApi.list).mockResolvedValue([task()]);
  vi.mocked(schedulesApi.create).mockResolvedValue(task({ id: 2 }));
  vi.mocked(schedulesApi.update).mockResolvedValue(task({ enabled: false }));
  vi.mocked(schedulesApi.runNow).mockResolvedValue(task());
  vi.mocked(schedulesApi.remove).mockResolvedValue(undefined);
});

afterEach(() => vi.clearAllMocks());

async function expand() {
  render(<AgentScheduledTasks slug="backend-julio" />);
  await userEvent.click(screen.getByRole("button", { name: /Agendamentos/ }));
  await screen.findByText("Resumo diário");
}

describe("AgentScheduledTasks", () => {
  it("lazy-loads schedules on expand", async () => {
    await expand();
    expect(schedulesApi.list).toHaveBeenCalledWith("backend-julio");
    expect(screen.getByText("Resumo diário")).toBeInTheDocument();
  });

  it("creates a read-only schedule", async () => {
    await expand();
    await userEvent.type(screen.getByLabelText("Nome do agendamento"), "Standup");
    await userEvent.type(screen.getByLabelText("Especificação do agendamento"), "1800");
    await userEvent.type(screen.getByLabelText("Prompt da tarefa"), "poste o status");
    await userEvent.click(screen.getByRole("button", { name: "Criar agendamento" }));
    expect(schedulesApi.create).toHaveBeenCalledWith("backend-julio", {
      name: "Standup",
      kind: "interval",
      spec: "1800",
      prompt: "poste o status",
      tools: "read",
    });
  });

  it("gates write tools behind the confirmation checkbox", async () => {
    await expand();
    await userEvent.type(screen.getByLabelText("Nome do agendamento"), "Build");
    await userEvent.type(screen.getByLabelText("Especificação do agendamento"), "3600");
    await userEvent.type(screen.getByLabelText("Prompt da tarefa"), "rode o build");
    await userEvent.selectOptions(screen.getByLabelText("Ferramentas da tarefa"), "write");
    const submit = screen.getByRole("button", { name: "Criar agendamento" });
    expect(submit).toBeDisabled(); // write requires the confirm
    await userEvent.click(screen.getByRole("checkbox"));
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    expect(schedulesApi.create).toHaveBeenCalledWith(
      "backend-julio",
      expect.objectContaining({ tools: "write" }),
    );
  });

  it("runs a schedule now", async () => {
    await expand();
    await userEvent.click(screen.getByRole("button", { name: "Executar agora" }));
    expect(schedulesApi.runNow).toHaveBeenCalledWith(1);
  });

  it("toggles and deletes", async () => {
    await expand();
    await userEvent.click(screen.getByRole("button", { name: "Desativar" }));
    expect(schedulesApi.update).toHaveBeenCalledWith(1, { enabled: false });
    await userEvent.click(screen.getByRole("button", { name: /Excluir agendamento/ }));
    expect(schedulesApi.remove).toHaveBeenCalledWith(1);
  });
});
