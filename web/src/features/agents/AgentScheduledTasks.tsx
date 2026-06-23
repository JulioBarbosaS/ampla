import { type FormEvent, useState } from "react";
import { type ScheduleInput, schedulesApi } from "../../lib/api/schedules";
import type { ScheduledTask, ScheduleKind } from "../../lib/api/types";

const KIND_HINT: Record<ScheduleKind, string> = {
  interval: "segundos entre execuções (ex.: 3600)",
  cron: "expressão cron UTC (ex.: 30 9 * * 1-5)",
  once: "instante ISO-8601 (ex.: 2026-07-01T09:00:00Z)",
};

function statusChip(status: string | null): { label: string; cls: string } {
  if (!status) return { label: "nunca executou", cls: "bg-zinc-800 text-zinc-400" };
  if (status === "ok") return { label: "ok", cls: "bg-emerald-900/50 text-emerald-300" };
  if (status === "running") return { label: "executando…", cls: "bg-amber-900/50 text-amber-300" };
  if (status === "failed" || status === "blocked")
    return { label: status, cls: "bg-red-900/50 text-red-300" };
  return { label: status.replace("skipped_", "pulado: "), cls: "bg-zinc-800 text-zinc-400" };
}

function fmt(ts: string | null): string {
  return ts ? new Date(ts).toLocaleString("pt-BR") : "—";
}

function TaskRow({ task, onChanged }: { task: ScheduledTask; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const chip = statusChip(task.last_status);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="space-y-1 rounded-md bg-zinc-900 px-3 py-2 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-zinc-200">{task.name}</span>
        {task.tools === "write" && (
          <span className="rounded bg-red-900/50 px-1.5 py-0.5 text-red-300">write</span>
        )}
        <span className={`rounded px-1.5 py-0.5 ${chip.cls}`}>{chip.label}</span>
        <span className="ml-auto font-mono text-zinc-500">
          {task.kind}: {task.spec}
        </span>
      </div>
      <p className="text-zinc-500">
        próxima: {fmt(task.next_run_at)} · última: {fmt(task.last_run_at)}
      </p>
      <div className="flex gap-2 pt-1">
        <button
          type="button"
          disabled={busy}
          onClick={() => act(() => schedulesApi.update(task.id, { enabled: !task.enabled }))}
          className="rounded bg-zinc-800 px-2 py-0.5 text-zinc-300 hover:bg-zinc-700 disabled:opacity-40"
        >
          {task.enabled ? "Desativar" : "Ativar"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => act(() => schedulesApi.runNow(task.id))}
          className="rounded bg-indigo-700 px-2 py-0.5 text-white hover:bg-indigo-600 disabled:opacity-40"
        >
          Executar agora
        </button>
        <button
          type="button"
          disabled={busy}
          aria-label={`Excluir agendamento ${task.name}`}
          onClick={() => act(() => schedulesApi.remove(task.id))}
          className="ml-auto rounded border border-red-800 px-2 py-0.5 text-red-300 hover:bg-red-950/40 disabled:opacity-40"
        >
          Excluir
        </button>
      </div>
    </li>
  );
}

/** "Agendamentos": scheduled agent tasks (Epic 08). The agent wakes on a schedule
 * and runs an owner-authored (trusted) prompt. Granting `write` is the danger
 * case (unattended writes) — gated behind an explicit confirmation. */
export function AgentScheduledTasks({ slug }: { slug: string }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<ScheduledTask[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [name, setName] = useState("");
  const [kind, setKind] = useState<ScheduleKind>("interval");
  const [spec, setSpec] = useState("");
  const [prompt, setPrompt] = useState("");
  const [tools, setTools] = useState<"read" | "write">("read");
  const [confirmWrite, setConfirmWrite] = useState(false);
  const [creating, setCreating] = useState(false);

  function load() {
    setError(null);
    setLoading(true);
    schedulesApi
      .list(slug)
      .then(setItems)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar."))
      .finally(() => setLoading(false));
  }

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && items === null && !loading) load();
  }

  async function create(e: FormEvent) {
    e.preventDefault();
    if (creating || !name.trim() || !spec.trim() || !prompt.trim()) return;
    if (tools === "write" && !confirmWrite) return;
    setCreating(true);
    setError(null);
    try {
      const data: ScheduleInput = { name: name.trim(), kind, spec: spec.trim(), prompt, tools };
      await schedulesApi.create(slug, data);
      setName("");
      setSpec("");
      setPrompt("");
      setTools("read");
      setConfirmWrite(false);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao criar o agendamento.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="mt-4 border-t border-zinc-800 pt-3">
      <button
        type="button"
        onClick={toggle}
        className="flex items-center gap-1 text-sm font-medium text-zinc-300 hover:text-zinc-100"
        aria-expanded={open}
      >
        <span className="text-zinc-500">{open ? "▾" : "▸"}</span> Agendamentos
      </button>
      {open && (
        <div className="mt-2 space-y-3">
          {error && (
            <p role="alert" className="text-xs text-red-400">
              {error}
            </p>
          )}
          {loading && items === null && <p className="text-xs text-zinc-500">carregando…</p>}
          {items?.length === 0 && (
            <p className="text-xs text-zinc-500">Nenhum agendamento ainda.</p>
          )}
          {items && items.length > 0 && (
            <ul className="space-y-1.5">
              {items.map((t) => (
                <TaskRow key={t.id} task={t} onChanged={load} />
              ))}
            </ul>
          )}

          <form onSubmit={create} className="space-y-2 rounded-md bg-zinc-900 p-3">
            <p className="text-xs font-medium text-zinc-400">Novo agendamento</p>
            <input
              aria-label="Nome do agendamento"
              placeholder="Nome (ex.: Resumo diário)"
              className="w-full rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-100"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <div className="flex gap-2">
              <select
                aria-label="Tipo de agendamento"
                className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-200"
                value={kind}
                onChange={(e) => setKind(e.target.value as ScheduleKind)}
              >
                <option value="interval">intervalo</option>
                <option value="cron">cron</option>
                <option value="once">uma vez</option>
              </select>
              <input
                aria-label="Especificação do agendamento"
                placeholder={KIND_HINT[kind]}
                className="min-w-0 flex-1 rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-100"
                value={spec}
                onChange={(e) => setSpec(e.target.value)}
              />
            </div>
            <textarea
              aria-label="Prompt da tarefa"
              placeholder="O que o agente deve fazer ao acordar…"
              className="min-h-[3.5rem] w-full rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-100"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
            <div className="flex items-center gap-2">
              <label className="text-xs text-zinc-400" htmlFor={`tools-${slug}`}>
                Ferramentas
              </label>
              <select
                id={`tools-${slug}`}
                aria-label="Ferramentas da tarefa"
                className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-200"
                value={tools}
                onChange={(e) => {
                  setTools(e.target.value as "read" | "write");
                  setConfirmWrite(false);
                }}
              >
                <option value="read">somente leitura</option>
                <option value="write">leitura + escrita</option>
              </select>
            </div>
            {tools === "write" && (
              <label className="flex items-start gap-2 text-xs text-red-300">
                <input
                  type="checkbox"
                  checked={confirmWrite}
                  onChange={(e) => setConfirmWrite(e.target.checked)}
                />
                <span>
                  Entendo que este agente poderá <strong>escrever arquivos</strong> sem supervisão
                  no horário agendado.
                </span>
              </label>
            )}
            <button
              type="submit"
              disabled={
                creating ||
                !name.trim() ||
                !spec.trim() ||
                !prompt.trim() ||
                (tools === "write" && !confirmWrite)
              }
              className="rounded bg-indigo-600 px-3 py-1 text-sm text-white disabled:opacity-40"
            >
              Criar agendamento
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
